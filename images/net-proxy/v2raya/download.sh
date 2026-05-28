#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "================================================================"
echo " Starting direct download of core components from GitHub"
echo " (With robust anti-reset and retry mechanisms enabled)"
echo "================================================================"

# 1. Create and enter the 'files' directory automatically
mkdir -p files
cd files || exit 1

# Define robust curl options: 5 retries, 3s delay, 15s timeout
# [Critical]: Use --http1.1 to bypass GitHub HTTP/2 stream reset errors
CURL_OPTS="-L --http1.1 --retry 5 --retry-delay 3 --connect-timeout 15"

# 2. Download Loyalsoldier enhanced rule files
echo "➤ Downloading GeoIP and Geosite rule files..."
curl $CURL_OPTS -o geoip.dat "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
curl $CURL_OPTS -o geosite.dat "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"

# 3. Download and extract Xray-core
echo "➤ Downloading Xray-core..."
curl $CURL_OPTS -o xray.zip "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
echo "➤ Extracting Xray..."
unzip -j -o xray.zip xray -d .
rm -f xray.zip

# 4. Fetch the latest release URL and download v2rayA
echo "➤ Fetching the latest v2rayA release URL..."
V2RAYA_RAW_URL=$(curl -s https://api.github.com/repos/v2rayA/v2rayA/releases/latest | grep "browser_download_url.*v2raya_linux_x64" | head -n 1 | cut -d '"' -f 4)
echo "➤ Downloading v2rayA..."
curl $CURL_OPTS -o v2raya "${V2RAYA_RAW_URL}"

# 5. Fetch the latest release URL, download, and extract sing-box
echo "➤ Fetching the latest sing-box release URL..."
SINGBOX_URL=$(curl -s https://api.github.com/repos/SagerNet/sing-box/releases/latest | grep "browser_download_url.*linux-amd64.tar.gz" | head -n 1 | cut -d '"' -f 4)
echo "➤ Downloading sing-box..."
curl $CURL_OPTS -o sing-box.tar.gz "${SINGBOX_URL}"
echo "➤ Extracting sing-box..."
tar -zxvf sing-box.tar.gz
mv sing-box-*-linux-amd64/sing-box .
# Clean up unnecessary archives and extracted folders
rm -rf sing-box-*-linux-amd64 sing-box.tar.gz

# 6. Grant execution permissions to all binaries
echo "➤ Granting execution permissions..."
chmod +x v2raya xray sing-box

# Return to the parent directory
cd ..

echo "================================================================"
echo " 🎉 All files downloaded successfully and stored in files/ "
echo "================================================================"
ls -lh files/