# RDMAss
A Python discord bot creating an interaction with RDM API

# Requirements - Pre Setup:
- Must be on Developemnt build of RDM
- Python3.6 >
- Create a Discord Bot (https://discord.com/developers/applications/)<br>
-- Make a note of your Discord Bot Token and Client ID.<br>
-- Make sure to enable [PRESENCE INTENT] [SERVER MEMBERS INTENT] [MESSAGE CONTENT INTENT]
- Add the discord bot to your server (must have slash commands privilages)<br>
-- (https://discord.com/api/oauth2/authorize?client_id=123456789012345678&permissions=8&scope=bot%20applications.commands)<br>
-- (change the `client_id` in the url to that of your Bots ID.


# Setup:
`git clone https://github.com/Pupitar/RDMAss.git`<br>
`cd RDMAss`<br>
`pip3 install -r requirements.txt`<br>
`cp config.example.json config.json`<br>

# Fill in the Config file:
```json
{
    "bot": {
        "token": "bot_token", // Add your Discord Bot Token
        "hide_bot_message": true // hide the bot mesage - true | false
    },
    "instance": {
        "discord": {
            "guild_id": 1234567890, // Add the Discord Guild ID for the server the bot will be run on
            "output_channel": 2345678901, // Create a discord channel where your commands will be issues and add the channel ID here
            "enabled_roles": [3456789012, 4567890123] // Discord Role ID's that you authorise to use the bot.
        },
        "rdm": {
            "api_endpoint": "http://127.0.0.1:9000", // RDM front end Endpoint
            "username": "rdm_root_user", // RDM front end user (must have admin permissions)
            "password": "6d9fdb16ed509488eeef6af2f842a744" // Password for the front end user
        }
    },
    "locale": {
        "date_format": "YYYY.MM.DD", // Date format
        "time_format": "HH:mm:ss", // Time format
        "timezone": "UTC" // Timezone (used for assignement scheduler)
    }
}
```

# Start:
`python3 main.py`

# Run in PM2:
Start RDMAss in PM2 with `pm2 start main.py --name RDMAss --interpreter python3` from the root folder of RDMAss<p>
Or you can copy and paste the following code below into an existing PM2 ecosystem file or start a new one in the root of RDMAss `ecosystem.config.js`.<br>
(remember to change the location of ` cwd: "/home/user/RDMAss/",` to your own directory.

```
module.exports = {
  apps: [
    {
      name: "RDMAss",
      script: "python3 main.py",
      cwd: "/home/user/RDMAss/",
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
