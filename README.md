# RDMAss
A Python Discord bot creating an interaction with RDM API.

### Features
- Assignment Groups scheduled & instant
- RDM Status
- Clear All Quests
- Reload All Instances

## Requirements
- RDM
- At least Python3.6 (virtualenv optional but welcome)
- Discord Bot Token (enable presence intent, server members intent, message content intent and slash commands privileges)

## Quick Setup
1. Fetch repo, install packages from `requirements.txt` and copy `config.example.json` to `config.json`
2. Edit `config.json`
3. Start `main.py`


## Detailed Setup

### 1. Fetch & install
```sh
git clone https://github.com/Pupitar/RDMAss.git rdmass && \
cd rdmass && \
pip3 install -r requirements.txt && \
cp config.example.json config.json
```

### 2. Edit config file

Additonal options are available in `default.json`

```json
{
    "bot": {
        "token": "bot_token",                              // Discord Bot Token
        "hide_bot_message": true                           // Hide the bot mesage - true | false
    },
    "instance": {
        "discord": {
            "guild_id": 1234567890,                        // Add the Discord Guild ID for the server the bot will be run on
            "enabled_roles": [3456789012, 4567890123],     // Discord Role ID's that you authorise to use the commands.
            "tech_channel": 2345678901                     // A discord channel where technical messages of scheduled jobs will be sent.
        },
        "rdm": {
            "api_endpoint": "http://127.0.0.1:9000",       // RDM front end Endpoint
            "username": "rdm_root_user",                   // RDM front end user (must have admin permissions)
            "password": "6d9fdb16ed509488eeef6af2f842a744" // Password for the front end user
        }
    },
    "locale": {
        "date_format": "YYYY.MM.DD",                       // Date format
        "time_format": "HH:mm",                            // Time format
        "timezone": "UTC"                                  // Timezone (used for assignement scheduler)
    }
}
```

### 3. Starting

#### Directly

`python3 main.py`

#### PM2
Start RDMAss in PM2 with `pm2 start main.py --name RDMAss --interpreter python3` from the root folder of RDMAss<p>
Or you can copy and paste the following code below into an existing PM2 ecosystem file or start a new one in the root of RDMAss `ecosystem.config.js` (remember to change the location of ` cwd: "/home/user/RDMAss/",` to your own directory.

```
module.exports = {
  apps: [
    {
      name: "RDMAss",
      script: "python3 main.py",
      cwd: "/home/user/rdmass/",
      instances: 1,
      autorestart: true,
      max_memory_restart: "1G",
      env_production: {
        NODE_ENV: "production",
      },
    },
  ],
};
```

#### systemd
    
Systemd __user__ service template. Read for [details](https://wiki.archlinux.org/title/systemd/User)

```
[Unit]
Description=rdmass
After=network.target

[Service]
ExecStart=python3 main.py
WorkingDirectory=/home/user/rdmass
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=default.target
```
