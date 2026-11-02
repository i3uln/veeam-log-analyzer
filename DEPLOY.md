# 사내 vSphere 배포 가이드

팀원들이 브라우저로 접속해서 쓸 수 있도록, 사내 vSphere에 리눅스 VM 하나를 만들어 배포합니다.

## 0. 시작 전 확인 (가장 중요)

- [ ] **회사 승인**: 고객 로그 일부가 외부 API(api.anthropic.com)로 전송됩니다. 보안 담당자와 협의하세요.
- [ ] **외부 통신**: VM에서 `https://api.anthropic.com` (443) 으로 나가는 통신이 방화벽/프록시에서 허용돼야 합니다.
- [ ] **API 비용 주체**: 개인 키가 아니라 팀/회사 계정의 키를 쓰는 게 맞습니다. Console에서 월 한도를 꼭 설정하세요.

## 1. VM 사양

| 항목 | 값 |
|---|---|
| OS | Ubuntu Server 24.04 LTS |
| vCPU / RAM | 2 vCPU / 4 GB |
| 디스크 | 30 GB (로그는 저장하지 않음) |
| 네트워크 | 사내망 전용, 외부 443 아웃바운드만 허용 |

## 2. 설치

```bash
sudo apt update && sudo apt install -y python3-venv nginx apache2-utils
sudo useradd -r -m -d /opt/veeam-log-analyzer veeamlog
sudo -u veeamlog bash -c '
  cd /opt/veeam-log-analyzer
  # 프로젝트 파일 복사 (scp, git clone 등)
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt
'
```

## 3. API 키 저장 (코드에 넣지 않음)

```bash
sudo bash -c 'echo "ANTHROPIC_API_KEY=sk-ant-..." > /etc/veeam-log-analyzer.env'
sudo chown root:veeamlog /etc/veeam-log-analyzer.env
sudo chmod 640 /etc/veeam-log-analyzer.env
```

회사 프록시를 거쳐야 하면 같은 파일에 `HTTPS_PROXY=http://proxy.corp.local:8080` 도 추가하세요.

## 4. 서비스 등록 (재부팅해도 자동 실행)

`/etc/systemd/system/veeam-log-analyzer.service`

```ini
[Unit]
Description=Veeam Log Analyzer
After=network-online.target

[Service]
User=veeamlog
WorkingDirectory=/opt/veeam-log-analyzer
EnvironmentFile=/etc/veeam-log-analyzer.env
ExecStart=/opt/veeam-log-analyzer/venv/bin/streamlit run app.py \
  --server.address 127.0.0.1 --server.port 8501 \
  --server.maxUploadSize 200 --browser.gatherUsageStats false
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now veeam-log-analyzer
```

## 5. nginx + 로그인 (Streamlit은 자체 로그인이 없음)

```bash
sudo htpasswd -c /etc/nginx/.htpasswd teamuser
```

`/etc/nginx/sites-available/veeam-log-analyzer`

```nginx
server {
    listen 80;
    server_name veeamlog.corp.local;

    client_max_body_size 200M;
    auth_basic "Veeam Log Analyzer";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;     # Streamlit은 웹소켓 사용
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/veeam-log-analyzer /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

사내 인증서가 있으면 443(HTTPS)으로 바꾸는 것을 권장합니다.

## 6. 확인

- 브라우저에서 `http://veeamlog.corp.local` 접속 → 로그인 → 샘플 로그 업로드
- 서비스 로그: `sudo journalctl -u veeam-log-analyzer -f`
