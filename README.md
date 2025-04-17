# SDWikiBot
The discord bot for the [SimDemocracy Wiki](https://simdemocracy.miraheze.org/wiki/Main_Page).

## Build
**This project requires Python 3.8+**

> Step 1 (optional): You are advised to create a virtual environment for this project. You can do so by running:
```
python -m venv .venv
```
Doing so will initalize your virtual environment in the `.venv` folder. You may change the folder parameter to a folder you wish or `.` for the current folder.

> Step 2: Install dependencies using `pip`
```
pip install -U -r requirements.txt
```

> Step 3: Obtain Discord bot API token. You may obtain this from the [Discord Developer Portal](https://discord.dev/applications).

> Step 4: Once you obtain the token, rename `.env.example` to `.env`. Replace the text `YOUR-TOKEN-HERE` with your bot token, such that it appears as so:
```
TOKEN=Od1s24.........
```
Save the `.env` file.

> Step 5: Run the bot
```
python -m main
```
