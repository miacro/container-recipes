#!/usr/bin/env bash

# 设置报错即退出
set -e

echo "========================================="
echo "  开始直连 GitHub 下载 v2rayA + Xray 组件  "
echo "========================================="

# 定义通用的 curl 参数：允许重试 5 次，每次重试间隔 3 秒，显示错误信息
CURL_OPTS="-L --retry 5 --retry-delay 3 --connect-timeout 15"

# 1. 下载 Loyalsoldier 社区增强版规则文件
echo "正在直连下载 GeoIP 和 Geosite 规则文件..."
curl $CURL_OPTS -o geoip.dat "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
curl $CURL_OPTS -o geosite.dat "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"

# 2. 下载 Xray-core 二进制文件并解压
echo "正在直连下载 Xray-core..."
curl $CURL_OPTS -o xray.zip "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
echo "正在解压 Xray..."
unzip -j -o xray.zip xray -d .
rm -f xray.zip

# 3. 动态获取并下载 v2rayA 二进制文件
echo "正在获取 v2rayA 最新版本链接..."
# 这一步同样直连 GitHub API 获取最新的 browser_download_url
V2RAYA_RAW_URL=$(curl -s https://api.github.com/repos/v2rayA/v2rayA/releases/latest | grep "browser_download_url.*v2raya_linux_x64" | head -n 1 | cut -d '"' -f 4)

echo "正在直连下载 v2rayA..."
curl $CURL_OPTS -o v2raya "${V2RAYA_RAW_URL}"

echo "正在赋予执行权限..."
chmod +x v2raya
chmod +x xray

echo "========================================="
echo "       所有文件直连下载完成，目录已就绪!       "
echo "========================================="
ls -lh geoip.dat geosite.dat v2raya xray