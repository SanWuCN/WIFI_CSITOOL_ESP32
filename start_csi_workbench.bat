@echo off
cd /d "%~dp0"
py -3.9 -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.9 tools\csi_workbench.py
