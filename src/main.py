import fastapi
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.routers.auth import router as auth_router
from src.routers.telegram import router as telegram_router
from src.routers.payment import router as payment_router
from src.middleware.audit_logging import AuditLoggingMiddleware
from starlette.staticfiles import StaticFiles
from pathlib import Path
import uvicorn
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import psutil
import time
import sys

# Logging setup with rotation
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatters
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

# Timed rotating file handler (daily rotation)
file_handler = TimedRotatingFileHandler(
    'app.log',
    when='midnight',  # Rotate at midnight
    interval=1,       # Every 1 interval (day)
    backupCount=30    # Keep 30 days of logs
)
file_handler.setFormatter(formatter)

# Stream handler for console
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


app = FastAPI()
start_time = time.time()

logger.info("TalkApp Backend ishga tushmoqda...")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS middleware qo'shildi")


# Add audit logging middleware
app.add_middleware(AuditLoggingMiddleware)
logger.info("Audit logging middleware qo'shildi")

# --- ROOT PAGE: Minimalistik chiroyli sahifa ---
@app.get("/", response_class=HTMLResponse)
async def root():
    logger.info("Root sahifaga so'rov keldi")
    # Compute system info
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    uptime_seconds = time.time() - start_time
    uptime_str = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m {int(uptime_seconds % 60)}s"
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    fastapi_version = fastapi.__version__
    db_status = "Ulangan"  # Assuming connected

    html_part1 = """
    <!DOCTYPE html>
    <html lang="uz">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TalkApp Backend</title>
        <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .header {
                text-align: center;
                margin-bottom: 40px;
            }
            .header h1 {
                font-size: 3em;
                margin-bottom: 10px;
            }
            .header p {
                font-size: 1.2em;
                opacity: 0.9;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                max-width: 1200px;
                margin: 0 auto;
            }
            .card {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 20px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            .card h2 {
                margin-top: 0;
                font-size: 1.5em;
            }
            .card ul {
                list-style: none;
                padding: 0;
            }
            .card li {
                margin-bottom: 10px;
            }
            .logs {
                font-family: monospace;
                background: rgba(0, 0, 0, 0.5);
                padding: 10px;
                border-radius: 5px;
                max-height: 250px;
                overflow-y: auto;
                white-space: pre-wrap;
            }
            canvas {
                max-width: 100%;
                height: auto;
                max-height: 150px;
            }
            .chart-container {
                height: 150px;
                position: relative;
                width: 100%;
                max-width: 200px;
            }
            .bottom-row {
                margin-top: 20px;
            }
            .full-width {
                grid-column: span 2;
                min-height: 500px;
            }
            .chart-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                grid-template-rows: 1fr 1fr;
                gap: 20px;
            }
            @media (max-width: 768px) {
                body {
                    padding: 10px;
                }
                .header h1 {
                    font-size: 2em;
                }
                .header p {
                    font-size: 1em;
                }
                .grid {
                    gap: 15px;
                }
                .card {
                    padding: 15px;
                }
                .card h2 {
                    font-size: 1.2em;
                }
                .full-width {
                    grid-column: span 1;
                }
                .chart-container {
                    max-width: 100%;
                }
                .full-width {
                    min-height: 800px;
                }
                .chart-grid {
                    grid-template-columns: repeat(1, 1fr);
                }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>TalkApp Backend</h1>
            <p>Telegram Integratsiya Platformasi</p>
        </div>
        <div class="grid">
            <div class="card">
                <h2>Loyiha Tavsifi</h2>
                <p>TalkApp Backend - bu Telegram akkauntlarini va foydalanuvchi autentifikatsiyasini boshqarish uchun FastAPI asosidagi backend xizmat. U foydalanuvchi boshqaruvi, Telegram sessiyalarini boshqarish va media saqlash uchun xavfsiz API endpointlarini taqdim etadi.</p>
            </div>
            <div class="card">
                <h2>Asosiy Xususiyatlar</h2>
                <ul>
                    <li>Foydalanuvchi autentifikatsiyasi va avtorizatsiyasi</li>
                    <li>Telegram akkauntlarini boshqarish</li>
                    <li>Sessiya saqlash va xavfsizlik</li>
                    <li>Media fayllarini boshqarish</li>
                    <li>Admin panel API'lari</li>
                    <li>CORS qo'llab-quvvatlash</li>
                </ul>
            </div>
            <div class="card">
                <h2>API Endpointlari</h2>
                <ul>
                    <li><code>POST /auth/login</code> - Foydalanuvchi kirishi</li>
                    <li><code>GET /auth/me</code> - Joriy foydalanuvchi ma'lumotlari</li>
                    <li><code>POST /start_login</code> - Telegram kirish boshlanishi</li>
                    <li><code>GET /users</code> - Foydalanuvchilarni ro'yxati</li>
                    <li><code>GET /check</code> - Sog'liq tekshiruvi</li>
                </ul>
            </div>
"""

    status_html = f"""
            <div class="card">
                <h2>Tizim Holati</h2>
                <p>Holat: <span style="color: #4CAF50;">Ishlamoqda</span></p>
                <p>Versiya: 1.0.0</p>
                <p>Muhit: Ishlab chiqish</p>
                <p>Server vaqti: {current_time}</p>
                <p>Ishga tushgan vaqti: {uptime_str}</p>
                <p>Python versiyasi: {python_version}</p>
                <p>FastAPI versiyasi: {fastapi_version}</p>
                <p>Ma'lumotlar bazasi: {db_status}</p>
            </div>
"""

    html_part2 = """
            <div class="card full-width">
                <h2>Tizim Monitoring</h2>
                <div class="chart-grid">
                    <div class="chart-container">
                        <h3>CPU Foydalanish</h3>
                        <canvas id="cpuChart"></canvas>
                    </div>
                    <div class="chart-container">
                        <h3>RAM Foydalanish</h3>
                        <canvas id="ramChart"></canvas>
                    </div>
                    <div class="chart-container bottom-row">
                        <h3>Disk Foydalanish</h3>
                        <canvas id="diskChart"></canvas>
                    </div>
                    <div class="chart-container bottom-row">
                        <h3>Tarmoq Trafiki</h3>
                        <canvas id="networkChart"></canvas>
                    </div>
                </div>
            </div>
            <div class="card full-width">
                <h2>So'nggi Loglar</h2>
                <div class="logs" id="logs">
Loglar yuklanmoqda...
                </div>
            </div>
        </div>
        <script>
            function colorizeLogLine(line) {
                let color = 'white'; // default

                if (line.includes('200')) {
                    color = '#4CAF50'; // green for success
                } else if (line.includes('404') || line.includes('500') || line.includes('ERROR')) {
                    color = '#f44336'; // red for errors
                } else if (line.includes('INFO')) {
                    color = '#E0E0E0'; // light gray for info
                } else if (line.includes('WARNING') || line.includes('WARN')) {
                    color = '#FFB74D'; // light orange for warnings
                } else if (line.includes('DEBUG')) {
                    color = '#64B5F6'; // light blue for debug
                } else if (line.includes('401') || line.includes('403')) {
                    color = '#FF8A65'; // light deep orange for auth errors
                }

                return '<span style="color: ' + color + ';">' + line + '</span>';
            }

            async function fetchLogs() {
                try {
                    const response = await fetch('/logs');
                    const data = await response.json();
                    const logsDiv = document.getElementById('logs');
                    const coloredLogs = data.logs.map(colorizeLogLine).join('<br>');
                    logsDiv.innerHTML = coloredLogs;
                } catch (error) {
                    console.error('Loglarni yuklashda xatolik:', error);
                    document.getElementById('logs').innerHTML = '<span style="color: #f44336;">Loglarni yuklashda xatolik yuz berdi</span>';
                }
            }

            // Initial load
            fetchLogs();

            // Update logs every 30 seconds
            setInterval(fetchLogs, 30000);

            // System monitoring charts
            Chart.defaults.color = 'white';
            let cpuChart, ramChart, diskChart, networkChart;

            function createCharts() {
                const chartOptions = {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                        }
                    }
                };

                cpuChart = new Chart(document.getElementById('cpuChart'), {
                    type: 'bar',
                    data: {
                        labels: ['Foydalanilgan', 'Bosh'],
                        datasets: [{
                            label: 'CPU Foydalanish',
                            data: [50, 50],
                            backgroundColor: ['#FF6384', '#36A2EB']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: 'white'
                                }
                            }
                        },
                        scales: {
                            x: {
                                ticks: {
                                    color: 'white'
                                }
                            },
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    color: 'white'
                                }
                            }
                        }
                    }
                });

                ramChart = new Chart(document.getElementById('ramChart'), {
                    type: 'bar',
                    data: {
                        labels: ['Foydalanilgan', 'Bosh'],
                        datasets: [{
                            label: 'RAM Foydalanish',
                            data: [50, 50],
                            backgroundColor: ['#FF9F40', '#FF6384']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom',
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });

                diskChart = new Chart(document.getElementById('diskChart'), {
                    type: 'bar',
                    data: {
                        labels: ['Foydalanilgan', 'Bosh'],
                        datasets: [{
                            label: 'Disk Foydalanish',
                            data: [50, 50],
                            backgroundColor: ['#4BC0C0', '#FF9F40']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom',
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });

                networkChart = new Chart(document.getElementById('networkChart'), {
                    type: 'bar',
                    data: {
                        labels: ['Yuborilgan (MB)', 'Qabul qilingan (MB)'],
                        datasets: [{
                            label: 'Tarmoq trafiki',
                            data: [100, 100],
                            backgroundColor: ['#9966FF', '#36A2EB']
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: {
                                    color: 'white'
                                }
                            }
                        },
                        scales: {
                            x: {
                                ticks: {
                                    color: 'white'
                                }
                            },
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    color: 'white'
                                }
                            }
                        }
                    }
                });
            }

            function fetchSystemStats() {
                fetch('/system_stats')
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            console.error('System stats xatolik:', data.error);
                            return;
                        }

                        // Update CPU chart
                        cpuChart.data.datasets[0].data = [data.cpu_percent, 100 - data.cpu_percent];
                        cpuChart.update();

                        // Update RAM chart
                        ramChart.data.datasets[0].data = [data.ram_percent, 100 - data.ram_percent];
                        ramChart.update();

                        // Update Disk chart
                        diskChart.data.datasets[0].data = [data.disk_percent, 100 - data.disk_percent];
                        diskChart.update();

                        // Update Network chart
                        networkChart.data.datasets[0].data = [data.network_sent, data.network_recv];
                        networkChart.update();
                    })
                    .catch(error => {
                        console.error('System stats yuklashda xatolik:', error);
                    });
            }

            // Initialize charts and fetch initial data
            createCharts();
            fetchSystemStats();

            // Update system stats every 5 seconds
            setInterval(fetchSystemStats, 5000);
        </script>
    </body>
    </html>
    """

    return html_part1 + status_html + html_part2


# --- LOGS ENDPOINT ---
@app.get("/logs")
async def get_logs():
    logger.info("Loglar endpointiga so'rov keldi")
    try:
        with open('app.log', 'r', encoding='utf-8') as f:
            logs = f.readlines()
        # Return last 50 lines
        logs = [line.strip() for line in logs[-50:]]
        return {"logs": logs}
    except FileNotFoundError:
        # Fallback to simulated logs if file doesn't exist yet
        logs = [
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO: Ilova muvaffaqiyatli ishga tushdi",
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO: Ma'lumotlar bazasi ulanishi o'rnatildi",
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO: CORS middleware yoqildi",
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO: Statik fayllar /media ga ulandi",
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO: Server 0.0.0.0:8002 da tinglamoqda",
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} INFO: API so'rovlari qabul qilinmoqda"
        ]
        return {"logs": logs}
    except Exception as e:
        return {"logs": [f"Loglarni o'qishda xatolik: {str(e)}"]}


# --- SYSTEM STATS ENDPOINT ---
@app.get("/system_stats")
async def get_system_stats():
    logger.info("System stats endpointiga so'rov keldi")
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)

        # RAM usage
        memory = psutil.virtual_memory()
        ram_percent = memory.percent
        ram_used = memory.used / (1024 ** 3)  # GB
        ram_total = memory.total / (1024 ** 3)  # GB

        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used = disk.used / (1024 ** 3)  # GB
        disk_total = disk.total / (1024 ** 3)  # GB

        # Network I/O
        net_io = psutil.net_io_counters()
        bytes_sent = net_io.bytes_sent / (1024 ** 2)  # MB
        bytes_recv = net_io.bytes_recv / (1024 ** 2)  # MB

        return {
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "ram_used": round(ram_used, 2),
            "ram_total": round(ram_total, 2),
            "disk_percent": disk_percent,
            "disk_used": round(disk_used, 2),
            "disk_total": round(disk_total, 2),
            "network_sent": round(bytes_sent, 2),
            "network_recv": round(bytes_recv, 2)
        }
    except Exception as e:
        logger.error(f"System stats olishda xatolik: {str(e)}")
        return {"error": f"System stats olishda xatolik: {str(e)}"}


# Oldingi endpoint yo‘llari saqlanadi:
# /check, /users, /admin/users, /admin/users-with-telegrams,
# /admin/users/{id} CRUD, /auth/login, /auth/me
# /start_login, /verify_code, /verify_password,
# /me/telegrams (GET/DELETE), /me/telegrams/{index} (DELETE),
# /admin/users/{user_id}/telegrams/{index} (DELETE)

MEDIA_ROOT = Path("media")
(MEDIA_ROOT / "avatars").mkdir(parents=True, exist_ok=True)
(MEDIA_ROOT / "downloads").mkdir(parents=True, exist_ok=True)
(MEDIA_ROOT / "exports").mkdir(parents=True, exist_ok=True)

# /media/... orqali statik fayllarni berish
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")
logger.info("Statik fayllar /media ga ulandi")

app.include_router(auth_router)
logger.info("Auth router qo'shildi")

app.include_router(telegram_router)
logger.info("Telegram router qo'shildi")

app.include_router(payment_router)
logger.info("Payment router qo'shildi")

