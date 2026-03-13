<div align="center">

# 👻 Kiro Gateway

**Gateway proxy untuk Kiro API (Amazon Q Developer / AWS CodeWhisperer)**

[🇬🇧 English](../../README.md) • [🇷🇺 Русский](../ru/README.md) • [🇨🇳 中文](../zh/README.md) • [🇪🇸 Español](../es/README.md) • [🇧🇷 Português](../pt/README.md) • [🇯🇵 日本語](../ja/README.md) • [🇰🇷 한국어](../ko/README.md)

Dibuat dengan ❤️ oleh [@Jwadow](https://github.com/jwadow)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Sponsor](https://img.shields.io/badge/💖_Sponsor-Dukung_Pengembangan-ff69b4)](#-dukung-proyek)

*Gunakan model Claude dari Kiro dengan Claude Code, OpenCode, Codex app, Cursor, Cline, Roo Code, Kilo Code, Obsidian, OpenAI SDK, LangChain, Continue dan alat lain yang kompatibel dengan OpenAI atau Anthropic*

[Model](#-model-yang-didukung) • [Fitur](#-fitur) • [Mulai Cepat](#-mulai-cepat) • [Konfigurasi](#%EF%B8%8F-konfigurasi) • [💖 Dukung](#-dukung-proyek)

</div>

---

## 🤖 Model yang Tersedia

> ⚠️ **Penting:** Ketersediaan model bergantung pada paket Kiro Anda (gratis/berbayar). Gateway menyediakan akses ke model yang tersedia di IDE atau CLI Anda berdasarkan langganan Anda. Daftar di bawah menunjukkan model yang umumnya tersedia di **paket gratis**.

> 🔒 **Claude Opus 4.5** telah dihapus dari paket gratis pada 17 Januari 2026. Mungkin tersedia di paket berbayar — periksa daftar model di IDE/CLI Anda.

🚀 **Claude Sonnet 4.5** — Performa seimbang. Bagus untuk coding, menulis, dan tugas umum.

⚡ **Claude Haiku 4.5** — Secepat kilat. Sempurna untuk respons cepat, tugas sederhana, dan chat.

📦 **Claude Sonnet 4** — Generasi sebelumnya. Masih kuat dan andal untuk sebagian besar kasus penggunaan.

📦 **Claude 3.7 Sonnet** — Model lama. Tersedia untuk kompatibilitas mundur.

🐋 **DeepSeek-V3.2** — Model MoE terbuka (685B parameter, 37B aktif). Performa seimbang untuk coding, penalaran, dan tugas umum.

🧩 **MiniMax M2.1** — Model MoE terbuka (230B parameter, 10B aktif). Bagus untuk tugas kompleks, perencanaan, dan alur kerja multi-langkah.

🤖 **Qwen3-Coder-Next** — Model MoE terbuka (80B parameter, 3B aktif). Fokus pada coding. Sempurna untuk pengembangan dan proyek besar.

> 💡 **Resolusi Model Cerdas:** Gunakan format nama model apa pun — `claude-sonnet-4-5`, `claude-sonnet-4.5`, atau bahkan nama berversi seperti `claude-sonnet-4-5-20250929`. Gateway akan menormalisasi secara otomatis.

---

## ✨ Fitur

| Fitur | Deskripsi |
|-------|-----------|
| 🔌 **API kompatibel OpenAI** | Bekerja dengan alat apa pun yang kompatibel dengan OpenAI |
| 🔌 **API kompatibel Anthropic** | Endpoint native `/v1/messages` |
| 🌐 **Dukungan VPN/Proxy** | Proxy HTTP/SOCKS5 untuk jaringan terbatas |
| 🧠 **Pemikiran Diperluas** | Penalaran adalah eksklusif proyek kami |
| 👁️ **Dukungan Visi** | Kirim gambar ke model |
| 🛠️ **Pemanggilan Alat** | Mendukung pemanggilan fungsi |
| 💬 **Riwayat pesan lengkap** | Meneruskan konteks percakapan lengkap |
| 📡 **Streaming** | Dukungan streaming SSE penuh |
| 🔄 **Logika Retry** | Retry otomatis saat error (403, 429, 5xx) |
| 📋 **Daftar model diperluas** | Termasuk model berversi |
| 🔐 **Manajemen token cerdas** | Refresh otomatis sebelum kedaluwarsa |

---

## 🚀 Mulai Cepat

**Pilih metode deployment Anda:**
- 🐍 **Python Nativo** - Kontrol penuh, debugging mudah
- 🐳 **Docker** - Lingkungan terisolasi, deployment mudah → [lompat ke Docker](#-docker-deployment)

### Prasyarat

- Python 3.10+
- Salah satu dari berikut:
  - [Kiro IDE](https://kiro.dev/) dengan akun yang sudah login, ATAU
  - [Kiro CLI](https://kiro.dev/cli/) dengan AWS SSO (AWS IAM Identity Center, OIDC) - Builder ID gratis atau akun perusahaan

### Instalasi

```bash
# Clone repositori (memerlukan Git)
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway

# Atau unduh ZIP: Code → Download ZIP → ekstrak → buka folder kiro-gateway

# Instal dependensi
pip install -r requirements.txt

# Konfigurasi (lihat bagian Konfigurasi)
cp .env.example .env
# Salin dan edit .env dengan kredensial Anda

# Jalankan server
python main.py

# Atau dengan port kustom (jika 8000 sedang digunakan)
python main.py --port 9000
```

Server akan tersedia di `http://localhost:8000`

---

## ⚙️ Konfigurasi

### Opsi 1: File JSON Kredensial (Kiro IDE / Enterprise)

Tentukan path ke file kredensial:

Bekerja dengan:
- **Kiro IDE** (standar) - untuk akun pribadi
- **Enterprise** - untuk akun perusahaan dengan SSO

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# Password untuk melindungi server proxy ANDA (buat string aman apa pun)
# Anda akan menggunakan ini sebagai api_key saat menghubungkan ke gateway Anda
PROXY_API_KEY="my-super-secret-password-123"
```

<details>
<summary>📄 Format file JSON</summary>

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "profileArn": "arn:aws:codewhisperer:us-east-1:...",
  "region": "us-east-1",
  "clientIdHash": "abc123..."  // Optional: for corporate SSO setups
}
```

> **Catatan:** Jika Anda memiliki dua file JSON di `~/.aws/sso/cache/` (misalnya, `kiro-auth-token.json` dan file dengan nama hash), gunakan `kiro-auth-token.json` di `KIRO_CREDS_FILE`. Gateway akan secara otomatis memuat file lainnya.

</details>

### Opsi 2: Variabel Lingkungan (file .env)

Buat file `.env` di root proyek:

```env
# Wajib
REFRESH_TOKEN="kiro_refresh_token_anda"

# Password untuk melindungi server proxy ANDA (buat string aman apa pun)
PROXY_API_KEY="my-super-secret-password-123"

# Opsional
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
```

### Opsi 3: Kredensial AWS SSO (kiro-cli / Enterprise)

Jika Anda menggunakan `kiro-cli` atau Kiro IDE dengan AWS SSO (AWS IAM Identity Center), gateway akan secara otomatis mendeteksi dan menggunakan autentikasi yang sesuai.

Bekerja dengan akun Builder ID gratis dan akun perusahaan.

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/your-sso-cache-file.json"

# Password untuk melindungi server proxy ANDA
PROXY_API_KEY="my-super-secret-password-123"

# Catatan: PROFILE_ARN TIDAK diperlukan untuk AWS SSO (Builder ID dan akun perusahaan)
# Gateway akan bekerja tanpanya
```

<details>
<summary>📄 Format file JSON AWS SSO</summary>

File kredensial AWS SSO (dari `~/.aws/sso/cache/`) berisi:

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "region": "us-east-1",
  "clientId": "...",
  "clientSecret": "..."
}
```

**Catatan:** Pengguna AWS SSO (Builder ID dan akun perusahaan) TIDAK memerlukan `profileArn`. Gateway akan bekerja tanpanya (jika ditentukan, akan diabaikan).

</details>

<details>
<summary>🔍 Cara kerjanya</summary>

Gateway secara otomatis mendeteksi tipe autentikasi berdasarkan file kredensial:

- **Kiro Desktop Auth** (default): Digunakan ketika `clientId` dan `clientSecret` TIDAK ada
  - Endpoint: `https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
  
- **AWS SSO (OIDC)**: Digunakan ketika `clientId` dan `clientSecret` ada
  - Endpoint: `https://oidc.{region}.amazonaws.com/token`

Tidak perlu konfigurasi tambahan — cukup arahkan ke file kredensial Anda!

</details>

### Opsi 4: Database SQLite kiro-cli

Jika Anda menggunakan `kiro-cli` dan lebih suka menggunakan database SQLite-nya secara langsung:

```env
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"

# Password untuk melindungi server proxy ANDA
PROXY_API_KEY="my-super-secret-password-123"

# Catatan: PROFILE_ARN TIDAK diperlukan untuk AWS SSO (Builder ID dan akun perusahaan)
# Gateway akan bekerja tanpanya
```

<details>
<summary>📄 Lokasi database</summary>

| Alat CLI | Path Database |
|----------|---------------|
| kiro-cli | `~/.local/share/kiro-cli/data.sqlite3` |
| amazon-q-developer-cli | `~/.local/share/amazon-q/data.sqlite3` |

Gateway membaca kredensial dari tabel `auth_kv` yang menyimpan:
- `kirocli:odic:token` atau `codewhisperer:odic:token` — access token, refresh token, kedaluwarsa
- `kirocli:odic:device-registration` atau `codewhisperer:odic:device-registration` — client ID dan secret

Kedua format kunci didukung untuk kompatibilitas dengan versi kiro-cli yang berbeda.

</details>

### Mendapatkan Kredensial

**Untuk pengguna Kiro IDE:**
- Login ke Kiro IDE dan gunakan Opsi 1 di atas (file JSON kredensial)
- File kredensial dibuat secara otomatis setelah login

**Untuk pengguna Kiro CLI:**
- Login dengan `kiro-cli login` dan gunakan Opsi 3 atau Opsi 4 di atas
- Tidak perlu ekstraksi token manual!

<details>
<summary>🔧 Lanjutan: Ekstraksi token manual</summary>

Jika Anda perlu mengekstrak refresh token secara manual (misalnya, untuk debugging), Anda dapat mencegat traffic Kiro IDE:
- Cari request ke: `prod.us-east-1.auth.desktop.kiro.dev/refreshToken`

</details>

---

## 🐳 Docker Deployment

> **Deployment berbasis Docker.** Lebih suka Python nativo? Lihat [Mulai Cepat](#-mulai-cepat) di atas.

### Mulai Cepat

```bash
# 1. Clone dan konfigurasi
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# Edit .env dengan kredensial Anda

# 2. Jalankan dengan docker-compose
docker-compose up -d

# 3. Periksa status
docker-compose logs -f
curl http://localhost:8000/health
```

### Docker Run (Tanpa Compose)

<details>
<summary>🔹 Menggunakan Variabel Lingkungan</summary>

```bash
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="my-super-secret-password-123" \
  -e REFRESH_TOKEN="your_refresh_token" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest
```

</details>

<details>
<summary>🔹 Menggunakan File Kredensial</summary>

**Linux/macOS:**
```bash
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="my-super-secret-password-123" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest
```

**Windows (PowerShell):**
```powershell
docker run -d `
  -p 8000:8000 `
  -v ${HOME}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro `
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json `
  -e PROXY_API_KEY="my-super-secret-password-123" `
  --name kiro-gateway `
  ghcr.io/jwadow/kiro-gateway:latest
```

</details>

<details>
<summary>🔹 Menggunakan File .env</summary>

```bash
docker run -d -p 8000:8000 --env-file .env --name kiro-gateway ghcr.io/jwadow/kiro-gateway:latest
```

</details>

### Konfigurasi Docker Compose

Edit `docker-compose.yml` dan uncomment volume mounts untuk OS Anda:

```yaml
volumes:
  # Kredensial Kiro IDE (pilih OS Anda)
  - ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro              # Linux/macOS
  # - ${USERPROFILE}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro  # Windows
  
  # Database kiro-cli (pilih OS Anda)
  - ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Linux/macOS
  # - ${USERPROFILE}/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Windows
  
  # Debug logs (opsional)
  - ./debug_logs:/app/debug_logs
```

### Perintah Manajemen

```bash
docker-compose logs -f      # Lihat logs
docker-compose restart      # Restart
docker-compose down         # Stop
docker-compose pull && docker-compose up -d  # Update
```

<details>
<summary>🔧 Build dari Source</summary>

```bash
docker build -t kiro-gateway .
docker run -d -p 8000:8000 --env-file .env kiro-gateway
```

</details>

---

## 🌐 Dukungan VPN/Proxy

**Untuk pengguna di China, jaringan korporat, atau wilayah dengan masalah konektivitas ke layanan AWS.**

Gateway mendukung perutean semua permintaan Kiro API melalui server VPN atau proxy. Ini penting jika Anda mengalami masalah koneksi ke endpoint AWS atau perlu menggunakan proxy korporat.

### Konfigurasi

Tambahkan ke file `.env` Anda:

```env
# Proxy HTTP
VPN_PROXY_URL=http://127.0.0.1:7890

# Proxy SOCKS5
VPN_PROXY_URL=socks5://127.0.0.1:1080

# Dengan autentikasi (proxy korporat)
VPN_PROXY_URL=http://username:password@proxy.company.com:8080

# Tanpa protokol (default ke http://)
VPN_PROXY_URL=192.168.1.100:8080
```

### Protokol yang Didukung

- ✅ **HTTP** — Protokol proxy standar
- ✅ **HTTPS** — Koneksi proxy aman
- ✅ **SOCKS5** — Protokol proxy lanjutan (umum di software VPN)
- ✅ **Autentikasi** — Username/password tertanam di URL

### Kapan Anda Membutuhkannya

| Situasi | Solusi |
|---------|--------|
| Timeout koneksi ke AWS | Gunakan VPN/proxy untuk merutekan lalu lintas |
| Pembatasan jaringan korporat | Konfigurasi proxy perusahaan Anda |
| Masalah konektivitas regional | Gunakan layanan VPN dengan dukungan proxy |
| Persyaratan privasi | Rutekan melalui server proxy Anda sendiri |

### Software VPN Populer dengan Dukungan Proxy

Sebagian besar klien VPN menyediakan server proxy lokal:
- **Sing-box** — Klien VPN modern dengan dukungan proxy HTTP/SOCKS5
- **Clash** — Biasanya berjalan di `http://127.0.0.1:7890`
- **V2Ray** — Proxy SOCKS5/HTTP yang dapat dikonfigurasi
- **Shadowsocks** — Dukungan proxy SOCKS5
- **VPN Korporat** — Tanyakan departemen IT Anda untuk pengaturan proxy

Biarkan `VPN_PROXY_URL` kosong (default) jika Anda tidak memerlukan dukungan proxy.

---

## 📡 Referensi API

### Endpoint

| Endpoint | Metode | Deskripsi |
|----------|--------|-----------|
| `/` | GET | Health check |
| `/health` | GET | Health check detail |
| `/v1/models` | GET | Daftar model yang tersedia |
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/messages` | POST | Anthropic Messages API |

---

## 💡 Contoh Penggunaan

### OpenAI API

<details>
<summary>🔹 Request cURL Sederhana</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Halo!"}],
    "stream": true
  }'
```

> **Catatan:** Ganti `my-super-secret-password-123` dengan `PROXY_API_KEY` yang Anda atur di file `.env`.

</details>

<details>
<summary>🔹 Request dengan Streaming</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [
      {"role": "system", "content": "Kamu adalah asisten yang membantu."},
      {"role": "user", "content": "Berapa 2+2?"}
    ],
    "stream": true
  }'
```

</details>

<details>
<summary>🛠️ Dengan Pemanggilan Alat</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Bagaimana cuaca di London?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Dapatkan cuaca untuk suatu lokasi",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "Nama kota"}
          },
          "required": ["location"]
        }
      }
    }]
  }'
```

</details>

<details>
<summary>🐍 Python OpenAI SDK</summary>

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="my-super-secret-password-123"  # PROXY_API_KEY Anda dari .env
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[
        {"role": "system", "content": "Kamu adalah asisten yang membantu."},
        {"role": "user", "content": "Halo!"}
    ],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

</details>

<details>
<summary>🦜 LangChain</summary>

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="my-super-secret-password-123",  # PROXY_API_KEY Anda dari .env
    model="claude-sonnet-4-5"
)

response = llm.invoke("Halo, apa kabar?")
print(response.content)
```

</details>

### Anthropic API

<details>
<summary>🔹 Request cURL Sederhana</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Halo!"}]
  }'
```

> **Catatan:** Anthropic API menggunakan header `x-api-key` bukan `Authorization: Bearer`. Keduanya didukung.

</details>

<details>
<summary>🔹 Dengan System Prompt</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "system": "Kamu adalah asisten yang membantu.",
    "messages": [{"role": "user", "content": "Halo!"}]
  }'
```

> **Catatan:** Di Anthropic API, `system` adalah field terpisah, bukan pesan.

</details>

<details>
<summary>📡 Streaming</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "Halo!"}]
  }'
```

</details>

<details>
<summary>🐍 Python Anthropic SDK</summary>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="my-super-secret-password-123",  # PROXY_API_KEY Anda dari .env
    base_url="http://localhost:8000"
)

# Tanpa streaming
response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Halo!"}]
)
print(response.content[0].text)

# Dengan streaming
with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Halo!"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

</details>

---

## 🔧 Debugging

Logging debug **dinonaktifkan secara default**. Untuk mengaktifkan, tambahkan ke `.env` Anda:

```env
# Mode logging debug:
# - off: dinonaktifkan (default)
# - errors: simpan log hanya untuk request yang gagal (4xx, 5xx) - direkomendasikan untuk troubleshooting
# - all: simpan log untuk setiap request (ditimpa setiap request)
DEBUG_MODE=errors
```

### Mode Debug

| Mode | Deskripsi | Kasus Penggunaan |
|------|-----------|------------------|
| `off` | Dinonaktifkan (default) | Produksi |
| `errors` | Simpan log hanya untuk request yang gagal (4xx, 5xx) | **Direkomendasikan untuk troubleshooting** |
| `all` | Simpan log untuk setiap request | Pengembangan/debugging |

### File Debug

Ketika diaktifkan, request dicatat ke folder `debug_logs/`:

| File | Deskripsi |
|------|-----------|
| `request_body.json` | Request masuk dari klien (format OpenAI) |
| `kiro_request_body.json` | Request yang dikirim ke Kiro API |
| `response_stream_raw.txt` | Stream mentah dari Kiro |
| `response_stream_modified.txt` | Stream yang ditransformasi (format OpenAI) |
| `app_logs.txt` | Log aplikasi untuk request |
| `error_info.json` | Detail error (hanya saat error) |

---

## 📜 Lisensi

Proyek ini dilisensikan di bawah **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Ini berarti:
- ✅ Anda dapat menggunakan, memodifikasi, dan mendistribusikan software ini
- ✅ Anda dapat menggunakannya untuk tujuan komersial
- ⚠️ **Anda harus mengungkapkan kode sumber** ketika Anda mendistribusikan software
- ⚠️ **Penggunaan jaringan adalah distribusi** — jika Anda menjalankan versi yang dimodifikasi di server dan membiarkan orang lain berinteraksi dengannya, Anda harus membuat kode sumber tersedia untuk mereka
- ⚠️ Modifikasi harus dirilis di bawah lisensi yang sama

Lihat file [LICENSE](../../LICENSE) untuk teks lisensi lengkap.

### Mengapa AGPL-3.0?

AGPL-3.0 memastikan bahwa perbaikan pada software ini menguntungkan seluruh komunitas. Jika Anda memodifikasi gateway ini dan menerapkannya sebagai layanan, Anda harus membagikan perbaikan Anda dengan pengguna Anda.

### Perjanjian Lisensi Kontributor (CLA)

Dengan mengirimkan kontribusi ke proyek ini, Anda menyetujui ketentuan [Perjanjian Lisensi Kontributor (CLA)](../../CLA.md) kami. Ini memastikan bahwa:
- Anda memiliki hak untuk mengirimkan kontribusi
- Anda memberikan hak kepada pengelola untuk menggunakan dan melisensi ulang kontribusi Anda
- Proyek tetap dilindungi secara hukum

---

## 💖 Dukung Proyek

<div align="center">

<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Smilies/Smiling%20Face%20with%20Hearts.png" alt="Love" width="80" />

**Jika proyek ini menghemat waktu atau uang Anda, pertimbangkan untuk mendukungnya!**

Setiap kontribusi membantu menjaga proyek ini tetap hidup dan berkembang

<br>

### 🤑 Donasi

[**☕ Donasi Sekali**](https://app.lava.top/jwadow?tabId=donate) &nbsp;•&nbsp; [**💎 Dukungan Bulanan**](https://app.lava.top/jwadow?tabId=subscriptions)

<br>

### 🪙 Atau kirim crypto

| Mata Uang | Jaringan | Alamat |
|:---------:|:--------:|:-------|
| **USDT** | TRC20 | `TSVtgRc9pkC1UgcbVeijBHjFmpkYHDRu26` |
| **BTC** | Bitcoin | `12GZqxqpcBsqJ4Vf1YreLqwoMGvzBPgJq6` |
| **ETH** | Ethereum | `0xc86eab3bba3bbaf4eb5b5fff8586f1460f1fd395` |
| **SOL** | Solana | `9amykF7KibZmdaw66a1oqYJyi75fRqgdsqnG66AK3jvh` |
| **TON** | TON | `UQBVh8T1H3GI7gd7b-_PPNnxHYYxptrcCVf3qQk5v41h3QTM` |

</div>

---

## ⚠️ Penafian

Proyek ini tidak berafiliasi dengan, didukung oleh, atau disponsori oleh Amazon Web Services (AWS), Anthropic, atau Kiro IDE. Gunakan dengan risiko Anda sendiri dan sesuai dengan ketentuan layanan API yang mendasarinya.

---

<div align="center">

**[⬆ Kembali ke Atas](#-kiro-gateway)**

</div>
