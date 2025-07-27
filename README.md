# KOMAWAN Micro-CaaS

## Anggota Kelompok

| NIM      | Nama                          |
| -------- | ----------------------------- |
| 10122276 | Fikri Defi Wulanto            |
| 10122278 | Ibrahim Halim Mahmud          |
| 10122288 | Muhammad Rafli Fazrin         |
| 10122292 | Wildan Mujjahid Robbani       |
| 10122293 | Imat Imansyah                 |
| 10122297 | Dewa Ayu Sekar Purnama Devi   |
| 10122302 | Steave Imanuel                |
| 10122307 | Dhimas Kurnia Putra Supriyadi |
| 10122311 | Aldi Naufal                   |
| 10122480 | Paska Damarkus Sinaga         |

Micro-CaaS (Container as a Service) Dashboard berbasis Python & Flask untuk penyewaan server/container berbasis Docker. Tampilan modern, fitur lengkap, dan mudah dikembangkan.

## Fitur

- Deploy, stop, hapus, dan monitoring kontainer Docker
- Dashboard cyber security style (Tailwind CSS)
- Riwayat penyewaan & status kontainer (MySQL)
- Pencarian & filter kontainer
- Log aktivitas

## Teknologi

- Python 3.11+
- Flask
- Docker SDK for Python
- MySQL (mysql-connector-python)
- Tailwind CSS (CDN)

## Instalasi & Setup

### 1. Clone Repository

```bash
git clone https://github.com/wildanmujjahid29/KOMAWAN-Micro-CaaS.git
cd KOMAWAN-Micro-CaaS
```

### 2. Buat Virtual Environment (Opsional tapi disarankan)

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# atau
source venv/bin/activate  # Linux/Mac
```

### 3. Install Dependensi Python

```bash
pip install flask docker mysql-connector-python
```

### 4. Setup MySQL

- Install & jalankan MySQL Server
- Buat database baru:

```sql
CREATE DATABASE microiaas;
```

- (Opsional) Edit user/password di `app.py` bagian `MYSQL_CONFIG` jika perlu.

### 5. Jalankan Aplikasi

```bash
python app.py
```

Akses di browser: [http://localhost:5001](http://localhost:5001)

### 6. Pastikan Docker Desktop/Engine sudah running

## Struktur Project

```
├── app.py
├── templates/
│   └── index.html
├── .gitignore
└── README.md
```
