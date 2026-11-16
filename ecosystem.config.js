module.exports = {
  apps: [
    {
      name: "rfcat-tx-service",
      cwd: __dirname,
      script: "/bin/bash",
      args: [
        "-lc",
        [
          "set -euo pipefail",
          "if ! id -nG | tr ' ' '\\n' | grep -qx dialout; then",
          "  echo 'ERROR: PM2 user must be in the dialout group for RFCat USB access.' >&2",
          "  echo 'Run: sudo usermod -aG dialout $USER && re-login' >&2",
          "  exit 1",
          "fi",
          "source .venv/bin/activate",
          "exec ./rfcat-tx-service --host 0.0.0.0 --port 8080 -d manufacturers -v",
        ].join("\n"),
      ],
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      time: true,
      out_file: "./rfcat-tx-service.pm2.out.log",
      error_file: "./rfcat-tx-service.pm2.err.log",
      merge_logs: true,
    },
  ],
};
