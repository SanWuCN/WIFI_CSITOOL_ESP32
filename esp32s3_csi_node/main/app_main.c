/*
 * ESP32-S3 CSI node.
 *
 * One firmware supports TX and RX modes. Use the serial monitor to switch mode:
 *   mode tx
 *   mode rx
 */

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_check.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_idf_version.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "driver/rmt_tx.h"
#include "driver/uart_vfs.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "rom/ets_sys.h"

#define APP_DEFAULT_CHANNEL 11
#define APP_DEFAULT_TX_HZ 50
#define APP_MIN_TX_HZ 1
#define APP_MAX_TX_HZ 1000
#define APP_NVS_NAMESPACE "csi_node"
#define APP_TX_TASK_STACK 4096
#define APP_CMD_TASK_STACK 4096
#define APP_LED_TASK_STACK 2048
#define APP_RGB_GPIO 48
#define APP_RGB_LED_COUNT 1
#define APP_RGB_RMT_RESOLUTION_HZ 10000000
#define APP_TX_PAYLOAD_MAGIC 0x31534943u
#define APP_CSI_BIN_MAGIC 0x49435345u

#define APP_WIFI_BANDWIDTH WIFI_BW_HT40
#define APP_ESP_NOW_PHYMODE WIFI_PHY_MODE_HT40
#define APP_ESP_NOW_RATE WIFI_PHY_RATE_MCS0_LGI

static const char *TAG = "csi_node";
static const uint8_t APP_TX_MAC[] = {0x1a, 0x00, 0x00, 0x00, 0x00, 0x00};
static rmt_channel_handle_t g_led_chan = NULL;
static rmt_encoder_handle_t g_led_encoder = NULL;
static volatile uint32_t g_last_csi_tick = 0;

static const rmt_symbol_word_t ws2812_zero = {
    .level0 = 1,
    .duration0 = 0.3 * APP_RGB_RMT_RESOLUTION_HZ / 1000000,
    .level1 = 0,
    .duration1 = 0.9 * APP_RGB_RMT_RESOLUTION_HZ / 1000000,
};

static const rmt_symbol_word_t ws2812_one = {
    .level0 = 1,
    .duration0 = 0.9 * APP_RGB_RMT_RESOLUTION_HZ / 1000000,
    .level1 = 0,
    .duration1 = 0.3 * APP_RGB_RMT_RESOLUTION_HZ / 1000000,
};

static const rmt_symbol_word_t ws2812_reset = {
    .level0 = 0,
    .duration0 = APP_RGB_RMT_RESOLUTION_HZ / 1000000 * 50 / 2,
    .level1 = 0,
    .duration1 = APP_RGB_RMT_RESOLUTION_HZ / 1000000 * 50 / 2,
};

typedef enum {
    APP_MODE_RX = 0,
    APP_MODE_TX = 1,
    APP_MODE_STANDBY = 2,
} app_mode_t;

typedef enum {
    APP_OUTPUT_CSV = 0,
    APP_OUTPUT_BIN = 1,
} app_output_t;

typedef struct {
    app_mode_t mode;
    app_output_t output;
    uint8_t channel;
    uint16_t tx_hz;
} app_config_t;

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint32_t seq;
    uint32_t tx_timestamp_us;
} app_tx_payload_t;

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint16_t version;
    uint16_t header_len;
    uint16_t csi_len;
    uint16_t payload_len;
    uint32_t record_seq;
    uint32_t local_timestamp_us;
    uint32_t rx_timestamp_us;
    uint32_t tx_seq;
    uint32_t tx_timestamp_us;
    int8_t rssi;
    int8_t noise_floor;
    uint8_t rate;
    uint8_t sig_mode;
    uint8_t mcs;
    uint8_t bandwidth;
    uint8_t channel;
    int8_t secondary_channel;
    uint8_t smoothing;
    uint8_t not_sounding;
    uint8_t aggregation;
    uint8_t stbc;
    uint8_t fec_coding;
    uint8_t sgi;
    uint8_t ant;
    uint8_t first_word_invalid;
    uint8_t rx_state;
    uint8_t tx_payload_found;
    uint16_t tx_payload_offset;
    uint16_t sig_len;
    uint16_t ampdu_cnt;
    uint16_t reserved;
} app_csi_bin_header_t;

_Static_assert(sizeof(app_csi_bin_header_t) == 58, "Unexpected CSI binary header size");

static app_config_t g_cfg = {
    .mode = APP_MODE_RX,
    .output = APP_OUTPUT_CSV,
    .channel = APP_DEFAULT_CHANNEL,
    .tx_hz = APP_DEFAULT_TX_HZ,
};

static const char *mode_to_str(app_mode_t mode)
{
    if (mode == APP_MODE_TX) {
        return "tx";
    }
    if (mode == APP_MODE_STANDBY) {
        return "standby";
    }
    return "rx";
}

static const char *output_to_str(app_output_t output)
{
    return output == APP_OUTPUT_BIN ? "bin" : "csv";
}

static void str_to_lower(char *s)
{
    for (; *s; ++s) {
        *s = (char)tolower((unsigned char)*s);
    }
}

static wifi_second_chan_t secondary_channel_for(uint8_t channel)
{
    return channel <= 4 ? WIFI_SECOND_CHAN_ABOVE : WIFI_SECOND_CHAN_BELOW;
}

static size_t ws2812_encoder_callback(const void *data, size_t data_size,
                                      size_t symbols_written, size_t symbols_free,
                                      rmt_symbol_word_t *symbols, bool *done, void *arg)
{
    (void)arg;
    if (symbols_free < 8) {
        return 0;
    }

    size_t data_pos = symbols_written / 8;
    const uint8_t *data_bytes = (const uint8_t *)data;
    if (data_pos < data_size) {
        size_t symbol_pos = 0;
        for (int bitmask = 0x80; bitmask != 0; bitmask >>= 1) {
            symbols[symbol_pos++] = (data_bytes[data_pos] & bitmask) ? ws2812_one : ws2812_zero;
        }
        return symbol_pos;
    }

    symbols[0] = ws2812_reset;
    *done = true;
    return 1;
}

static void rgb_set(uint8_t red, uint8_t green, uint8_t blue)
{
    if (!g_led_chan || !g_led_encoder) {
        return;
    }

    uint8_t pixel[APP_RGB_LED_COUNT * 3] = {
        green,
        red,
        blue,
    };
    rmt_transmit_config_t tx_config = {
        .loop_count = 0,
    };
    ESP_ERROR_CHECK_WITHOUT_ABORT(rmt_transmit(g_led_chan, g_led_encoder, pixel, sizeof(pixel), &tx_config));
    ESP_ERROR_CHECK_WITHOUT_ABORT(rmt_tx_wait_all_done(g_led_chan, 100));
}

static void rgb_init(void)
{
    rmt_tx_channel_config_t tx_chan_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = APP_RGB_GPIO,
        .mem_block_symbols = 64,
        .resolution_hz = APP_RGB_RMT_RESOLUTION_HZ,
        .trans_queue_depth = 4,
    };
    esp_err_t err = rmt_new_tx_channel(&tx_chan_config, &g_led_chan);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "RGB RMT channel init failed: %s", esp_err_to_name(err));
        return;
    }

    rmt_simple_encoder_config_t encoder_config = {
        .callback = ws2812_encoder_callback,
    };
    err = rmt_new_simple_encoder(&encoder_config, &g_led_encoder);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "RGB RMT encoder init failed: %s", esp_err_to_name(err));
        return;
    }

    err = rmt_enable(g_led_chan);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "RGB RMT enable failed: %s", esp_err_to_name(err));
        return;
    }
    rgb_set(16, 0, 0);
}

static void led_task(void *arg)
{
    (void)arg;
    bool on = false;

    while (true) {
        if (g_cfg.mode == APP_MODE_TX) {
            on = !on;
            if (on) {
                rgb_set(0, 0, 24);
            } else {
                rgb_set(0, 0, 0);
            }
            vTaskDelay(pdMS_TO_TICKS(300));
            continue;
        }

        if (g_cfg.mode == APP_MODE_STANDBY) {
            rgb_set(8, 6, 0);
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }

        uint32_t now = xTaskGetTickCount();
        uint32_t last = g_last_csi_tick;
        if (last && now - last < pdMS_TO_TICKS(120)) {
            rgb_set(0, 48, 0);
            vTaskDelay(pdMS_TO_TICKS(80));
            rgb_set(0, 10, 0);
            vTaskDelay(pdMS_TO_TICKS(120));
        } else {
            rgb_set(0, 10, 0);
            vTaskDelay(pdMS_TO_TICKS(250));
        }
    }
}

static void print_help(void)
{
    printf("\nCommands:\n");
    printf("  help          Show this help\n");
    printf("  status        Show current mode, channel, and TX rate\n");
    printf("  mode tx       Save TX mode and reboot\n");
    printf("  mode rx       Save RX/CSI mode and reboot\n");
    printf("  mode standby  Save standby mode and reboot\n");
    printf("  output csv    Save CSV serial output and reboot\n");
    printf("  output bin    Save binary serial output and reboot\n");
    printf("  freq 100      Save TX frequency in Hz and reboot, range %d-%d\n", APP_MIN_TX_HZ, APP_MAX_TX_HZ);
    printf("  channel 11    Save Wi-Fi channel and reboot, range 1-13\n");
    printf("  reboot        Restart the board\n\n");
}

static void print_status(void)
{
    printf("CSI_NODE_STATUS mode=%s output=%s channel=%u tx_hz=%u tx_mac=" MACSTR "\n",
           mode_to_str(g_cfg.mode), output_to_str(g_cfg.output), g_cfg.channel, g_cfg.tx_hz, MAC2STR(APP_TX_MAC));
}

static void configure_console_line_endings(void)
{
    esp_line_endings_t tx_endings = g_cfg.output == APP_OUTPUT_BIN ? ESP_LINE_ENDINGS_LF : ESP_LINE_ENDINGS_CRLF;

    (void)uart_vfs_dev_port_set_tx_line_endings(0, tx_endings);
    usb_serial_jtag_vfs_set_tx_line_endings(tx_endings);
}

static esp_err_t config_load(app_config_t *cfg)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open(APP_NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err != ESP_OK) {
        return err;
    }

    uint8_t mode = APP_MODE_RX;
    uint8_t output = APP_OUTPUT_CSV;
    uint8_t channel = APP_DEFAULT_CHANNEL;
    uint16_t tx_hz = APP_DEFAULT_TX_HZ;

    (void)nvs_get_u8(nvs, "mode", &mode);
    (void)nvs_get_u8(nvs, "output", &output);
    (void)nvs_get_u8(nvs, "channel", &channel);
    (void)nvs_get_u16(nvs, "tx_hz", &tx_hz);
    nvs_close(nvs);

    if (mode == APP_MODE_TX) {
        cfg->mode = APP_MODE_TX;
    } else if (mode == APP_MODE_STANDBY) {
        cfg->mode = APP_MODE_STANDBY;
    } else {
        cfg->mode = APP_MODE_RX;
    }
    cfg->output = output == APP_OUTPUT_BIN ? APP_OUTPUT_BIN : APP_OUTPUT_CSV;
    cfg->channel = channel >= 1 && channel <= 13 ? channel : APP_DEFAULT_CHANNEL;
    cfg->tx_hz = tx_hz >= APP_MIN_TX_HZ && tx_hz <= APP_MAX_TX_HZ ? tx_hz : APP_DEFAULT_TX_HZ;
    return ESP_OK;
}

static esp_err_t config_save(const app_config_t *cfg)
{
    nvs_handle_t nvs;
    ESP_RETURN_ON_ERROR(nvs_open(APP_NVS_NAMESPACE, NVS_READWRITE, &nvs), TAG, "open NVS");
    ESP_RETURN_ON_ERROR(nvs_set_u8(nvs, "mode", (uint8_t)cfg->mode), TAG, "save mode");
    ESP_RETURN_ON_ERROR(nvs_set_u8(nvs, "output", (uint8_t)cfg->output), TAG, "save output");
    ESP_RETURN_ON_ERROR(nvs_set_u8(nvs, "channel", cfg->channel), TAG, "save channel");
    ESP_RETURN_ON_ERROR(nvs_set_u16(nvs, "tx_hz", cfg->tx_hz), TAG, "save tx_hz");
    ESP_RETURN_ON_ERROR(nvs_commit(nvs), TAG, "commit NVS");
    nvs_close(nvs);
    return ESP_OK;
}

static void save_and_restart(const app_config_t *cfg)
{
    ESP_ERROR_CHECK(config_save(cfg));
    printf("Saved. Restarting...\n");
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(300));
    esp_restart();
}

static void command_task(void *arg)
{
    (void)arg;
    char line[96];
    size_t len = 0;

    setvbuf(stdin, NULL, _IONBF, 0);
    print_help();
    print_status();
    printf("csi> ");
    fflush(stdout);

    while (true) {
        int ch = getchar();
        if (ch < 0) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        if (ch == '\r' || ch == '\n') {
            if (len == 0) {
                printf("csi> ");
                fflush(stdout);
                continue;
            }
            line[len] = 0;
            len = 0;
        } else if (ch == '\b' || ch == 0x7f) {
            if (len > 0) {
                len--;
            }
            continue;
        } else if (len < sizeof(line) - 1) {
            line[len++] = (char)ch;
            continue;
        } else {
            line[len] = 0;
            len = 0;
            printf("\nCommand too long\ncsi> ");
            fflush(stdout);
            continue;
        }

        str_to_lower(line);

        char *cmd = strtok(line, " \t");
        char *arg1 = strtok(NULL, " \t");
        if (!cmd) {
            printf("csi> ");
            fflush(stdout);
            continue;
        }

        if (!strcmp(cmd, "help") || !strcmp(cmd, "?")) {
            print_help();
        } else if (!strcmp(cmd, "status")) {
            print_status();
        } else if (!strcmp(cmd, "reboot")) {
            esp_restart();
        } else if (!strcmp(cmd, "mode")) {
            if (!arg1 || (strcmp(arg1, "tx") && strcmp(arg1, "rx") && strcmp(arg1, "standby"))) {
                printf("Usage: mode tx | mode rx | mode standby\n");
                continue;
            }
            app_config_t next = g_cfg;
            if (!strcmp(arg1, "tx")) {
                next.mode = APP_MODE_TX;
            } else if (!strcmp(arg1, "standby")) {
                next.mode = APP_MODE_STANDBY;
            } else {
                next.mode = APP_MODE_RX;
            }
            save_and_restart(&next);
        } else if (!strcmp(cmd, "output")) {
            if (!arg1 || (strcmp(arg1, "csv") && strcmp(arg1, "bin"))) {
                printf("Usage: output csv | output bin\n");
                continue;
            }
            app_config_t next = g_cfg;
            next.output = !strcmp(arg1, "bin") ? APP_OUTPUT_BIN : APP_OUTPUT_CSV;
            save_and_restart(&next);
        } else if (!strcmp(cmd, "freq")) {
            if (!arg1) {
                printf("Usage: freq 100\n");
                continue;
            }
            int value = atoi(arg1);
            if (value < APP_MIN_TX_HZ || value > APP_MAX_TX_HZ) {
                printf("Frequency must be in %d-%d Hz\n", APP_MIN_TX_HZ, APP_MAX_TX_HZ);
                continue;
            }
            app_config_t next = g_cfg;
            next.tx_hz = (uint16_t)value;
            save_and_restart(&next);
        } else if (!strcmp(cmd, "channel") || !strcmp(cmd, "ch")) {
            if (!arg1) {
                printf("Usage: channel 11\n");
                continue;
            }
            int value = atoi(arg1);
            if (value < 1 || value > 13) {
                printf("Channel must be in 1-13\n");
                continue;
            }
            app_config_t next = g_cfg;
            next.channel = (uint8_t)value;
            save_and_restart(&next);
        } else {
            printf("Unknown command: %s\n", cmd);
        }

        printf("csi> ");
        fflush(stdout);
    }
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, APP_WIFI_BANDWIDTH));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(g_cfg.channel, secondary_channel_for(g_cfg.channel)));

    if (g_cfg.mode == APP_MODE_TX) {
        ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA, APP_TX_MAC));
    }
}

static void esp_now_init_common(void)
{
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_set_pmk((const uint8_t *)"pmk1234567890123"));

    esp_now_peer_info_t peer = {
        .channel = APP_DEFAULT_CHANNEL,
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
        .peer_addr = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff},
    };
    peer.channel = g_cfg.channel;

    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

    esp_now_rate_config_t rate_config = {
        .phymode = APP_ESP_NOW_PHYMODE,
        .rate = APP_ESP_NOW_RATE,
        .ersu = false,
        .dcm = false,
    };
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(peer.peer_addr, &rate_config));
}

static void tx_task(void *arg)
{
    (void)arg;
    const uint8_t broadcast_addr[] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    const uint32_t delay_ms = 1000 / g_cfg.tx_hz > 0 ? 1000 / g_cfg.tx_hz : 1;

    ESP_LOGI(TAG, "TX started: channel=%u tx_hz=%u mac=" MACSTR,
             g_cfg.channel, g_cfg.tx_hz, MAC2STR(APP_TX_MAC));

    for (uint32_t seq = 0;; ++seq) {
        app_tx_payload_t payload = {
            .magic = APP_TX_PAYLOAD_MAGIC,
            .seq = seq,
            .tx_timestamp_us = (uint32_t)esp_timer_get_time(),
        };
        esp_err_t err = esp_now_send(broadcast_addr, (const uint8_t *)&payload, sizeof(payload));
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "ESP-NOW send failed: %s", esp_err_to_name(err));
        }
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
}

static bool find_tx_payload(const uint8_t *buf, uint16_t len, app_tx_payload_t *payload, uint16_t *offset)
{
    if (!buf || !payload || !offset || len < sizeof(app_tx_payload_t)) {
        return false;
    }

    for (uint16_t i = 0; i <= len - sizeof(app_tx_payload_t); ++i) {
        app_tx_payload_t candidate = {0};
        memcpy(&candidate, buf + i, sizeof(candidate));
        if (candidate.magic == APP_TX_PAYLOAD_MAGIC) {
            *payload = candidate;
            *offset = i;
            return true;
        }
    }
    return false;
}

static void csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    (void)ctx;
    if (!info || !info->buf) {
        return;
    }

    if (memcmp(info->mac, APP_TX_MAC, sizeof(APP_TX_MAC)) != 0) {
        return;
    }

    g_last_csi_tick = xTaskGetTickCount();

    const wifi_pkt_rx_ctrl_t *rx_ctrl = &info->rx_ctrl;
    app_tx_payload_t payload = {0};
    uint16_t payload_offset = 0xffff;
    bool has_payload = find_tx_payload(info->payload, info->payload_len, &payload, &payload_offset);
    uint32_t rx_timestamp_us = rx_ctrl->timestamp;

    static uint32_t s_count = 0;
    if (s_count == 0) {
        ESP_LOGI(TAG, "RX started: channel=%u listening_tx_mac=" MACSTR, g_cfg.channel, MAC2STR(APP_TX_MAC));
        if (g_cfg.output == APP_OUTPUT_CSV) {
            printf("type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,secondary_channel,local_timestamp,ant,sig_len,rx_state,tx_seq,tx_timestamp_us,rx_timestamp_us,tx_payload_found,tx_payload_offset,tx_payload_len,len,first_word,data\n");
        } else {
            printf("CSI_BINARY_STREAM version=1 header_len=%u magic=0x%08lx\n",
                   (unsigned int)sizeof(app_csi_bin_header_t), (unsigned long)APP_CSI_BIN_MAGIC);
        }
    }

    flockfile(stdout);
    if (g_cfg.output == APP_OUTPUT_BIN) {
        app_csi_bin_header_t header = {
            .magic = APP_CSI_BIN_MAGIC,
            .version = 1,
            .header_len = sizeof(app_csi_bin_header_t),
            .csi_len = info->len,
            .payload_len = info->payload_len,
            .record_seq = s_count,
            .local_timestamp_us = rx_ctrl->timestamp,
            .rx_timestamp_us = rx_timestamp_us,
            .tx_seq = has_payload ? payload.seq : 0,
            .tx_timestamp_us = has_payload ? payload.tx_timestamp_us : 0,
            .rssi = rx_ctrl->rssi,
            .noise_floor = rx_ctrl->noise_floor,
            .rate = rx_ctrl->rate,
            .sig_mode = rx_ctrl->sig_mode,
            .mcs = rx_ctrl->mcs,
            .bandwidth = rx_ctrl->cwb,
            .channel = rx_ctrl->channel,
            .secondary_channel = rx_ctrl->secondary_channel,
            .smoothing = rx_ctrl->smoothing,
            .not_sounding = rx_ctrl->not_sounding,
            .aggregation = rx_ctrl->aggregation,
            .stbc = rx_ctrl->stbc,
            .fec_coding = rx_ctrl->fec_coding,
            .sgi = rx_ctrl->sgi,
            .ant = rx_ctrl->ant,
            .first_word_invalid = info->first_word_invalid,
            .rx_state = rx_ctrl->sig_mode,
            .tx_payload_found = has_payload ? 1 : 0,
            .tx_payload_offset = has_payload ? payload_offset : 0xffff,
            .sig_len = rx_ctrl->sig_len,
            .ampdu_cnt = rx_ctrl->ampdu_cnt,
            .reserved = 0,
        };
        fwrite(&header, 1, sizeof(header), stdout);
        fwrite(info->buf, 1, info->len, stdout);
        fflush(stdout);
        funlockfile(stdout);
        s_count++;
        return;
    }

    printf("CSI_DATA,%lu," MACSTR ",%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%lu,%d,%d,%d,%lu,%lu,%lu,%u,%u,%u",
               (unsigned long)s_count,
               MAC2STR(info->mac),
               rx_ctrl->rssi,
               rx_ctrl->rate,
               rx_ctrl->sig_mode,
               rx_ctrl->mcs,
               rx_ctrl->cwb,
               rx_ctrl->smoothing,
               rx_ctrl->not_sounding,
               rx_ctrl->aggregation,
               rx_ctrl->stbc,
               rx_ctrl->fec_coding,
               rx_ctrl->sgi,
               rx_ctrl->noise_floor,
               rx_ctrl->ampdu_cnt,
               rx_ctrl->channel,
               rx_ctrl->secondary_channel,
               (unsigned long)rx_ctrl->timestamp,
               rx_ctrl->ant,
               rx_ctrl->sig_len,
               rx_ctrl->sig_mode,
               (unsigned long)(has_payload ? payload.seq : 0),
               (unsigned long)(has_payload ? payload.tx_timestamp_us : 0),
               (unsigned long)rx_timestamp_us,
               (unsigned int)(has_payload ? 1 : 0),
               (unsigned int)(has_payload ? payload_offset : 0xffff),
               (unsigned int)info->payload_len);

    printf(",%d,%d,\"[%d", info->len, info->first_word_invalid, info->buf[0]);
    for (int i = 1; i < info->len; i++) {
        printf(",%d", info->buf[i]);
    }
    printf("]\"\n");
    funlockfile(stdout);
    s_count++;
}

static void csi_init(void)
{
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_ERROR_CHECK(config_load(&g_cfg));
    configure_console_line_endings();
    ESP_LOGI(TAG, "Booting mode=%s channel=%u tx_hz=%u", mode_to_str(g_cfg.mode), g_cfg.channel, g_cfg.tx_hz);

    rgb_init();
    xTaskCreate(led_task, "led_task", APP_LED_TASK_STACK, NULL, 3, NULL);
    xTaskCreate(command_task, "command_task", APP_CMD_TASK_STACK, NULL, 5, NULL);

    if (g_cfg.mode == APP_MODE_TX) {
        wifi_init();
        esp_now_init_common();
        xTaskCreate(tx_task, "tx_task", APP_TX_TASK_STACK, NULL, 5, NULL);
    } else if (g_cfg.mode == APP_MODE_RX) {
        wifi_init();
        esp_now_init_common();
        csi_init();
    } else {
        ESP_LOGI(TAG, "Standby mode: Wi-Fi CSI/TX disabled");
    }
}
