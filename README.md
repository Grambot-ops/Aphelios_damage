# Aphelios DPS Build Optimizer

This project is a sophisticated Python script that calculates the optimal item build for the League of Legends champion Aphelios by simulating combat DPS. It uses the `cassiopeia` library to fetch live, up-to-date item and champion data directly from the Riot Games API, ensuring the calculations are always based on the current game patch.

The simulation is parallelized using multiprocessing to test tens of thousands of valid item combinations quickly and efficiently.

## Features

- **Live Game Data**: Pulls all item and champion statistics from Riot's Data Dragon, so it never goes out of date.
- **Stateful Simulation**: Accurately models complex mechanics like Crescendum chakram stacking and weapon ammo.
- **Parallel Processing**: Uses all available CPU cores to rapidly simulate thousands of builds.
- **User-Friendly Setup**: Includes interactive prompts for your Riot API key and server region.
- **Dependency Checking**: Automatically detects if `cassiopeia` is not installed and provides the correct installation command.

## Requirements

- Python 3.7+
- `pip` (Python's package installer)
- A valid Riot Games API Key. You can get one from the [Riot Developer Portal](https://developer.riotgames.com/).

## Setup and Installation

Follow these steps in your terminal to get the project running. Using a virtual environment is the recommended and safest way to handle Python projects, especially on systems like Arch Linux.

**1. Navigate to the Project Directory**

Open your terminal and `cd` into the folder where you saved the `Damage.py` script.

```bash
cd /path/to/your/Aphelios_damage
```

**2. Create a Python Virtual Environment**

This creates a self-contained environment for the project's dependencies, so they don't interfere with your system's Python packages.

```bash
python -m venv venv
```

**3. Activate the Virtual Environment**

You must activate the environment to use it.

```bash
source venv/bin/activate
```

Your terminal prompt should now be prefixed with `(venv)`, indicating the environment is active.

**4. Install Required Libraries**

With the environment active, use `pip` to install `cassiopeia`.

```bash
pip install cassiopeia
```

## How to Run the Script

Make sure your virtual environment is still active (`(venv)` is visible in your prompt). Then, simply run the Python script:

```bash
python Damage.py
```

The script will then guide you through the setup:

1.  It will first ask for your **Riot API Key**. Paste it in and press Enter. (Your input will be hidden for security).
2.  Next, it will ask for your **server region** (e.g., `EUW`, `NA`, `KR`).
3.  After that, it will fetch the latest game data and begin the simulation.

## Troubleshooting Guide

Here are solutions to the common errors encountered during the setup and execution of this script.

---

### Error 1: `ModuleNotFoundError: No module named 'cassiopeia'`

This is the most common error and happens when the script starts.

- **Symptom:** The script immediately exits and prints a message telling you to install `cassiopeia`.
- **Cause:** You have not installed the required library, or you have installed it in the wrong Python environment.
- **Solution:**
  1.  Make sure you have **activated the virtual environment** first by running `source venv/bin/activate` in the project directory.
  2.  Run the installation command: `pip install cassiopeia`.

---

### Error 2: `Failed to configure Cassiopeia or load data: ...`

This error occurs after you have entered your API key and region.

- **Symptom:** The script prints `[ERROR] Failed to configure Cassiopeia...` followed by a more specific message.
- **Possible Causes & Solutions:**

  1.  **Message: `object has already been loaded`**

      - _Cause:_ This is an internal state error in Cassiopeia that occurs when its settings are configured in multiple steps instead of all at once.
      - _Solution:_ The script has been fixed to use a single, atomic `cass.apply_settings()` call that includes the API key and region in one dictionary. This should no longer occur with the final version of the code.

  2.  **Message: `No source can provide "RealmData"`**

      - _Cause:_ You are telling Cassiopeia to use a custom data pipeline, but you have not included the essential `DDragon` source. `DDragon` is required to get basic game metadata like the current patch version, champion list, and item list.
      - _Solution:_ Your settings dictionary must define the full, standard pipeline. The corrected script now does this automatically.
        ```python
        "pipeline": {
            "Cache": {},
            "DDragon": {},
            "RiotAPI": { "api_key": api_key }
        }
        ```

  3.  **Message: `Data not found (404)` or `Forbidden (403)`**
      - _Cause:_ Your Riot API key is incorrect, has expired, or has been blacklisted.
      - _Solution:_
        - Go to the [Riot Developer Portal](https://developer.riotgames.com/) and verify your key is correct.
        - Generate a new key if it has expired.
        - Ensure you haven't exceeded your rate limits.

---

### Error 3: `FileNotFoundError: [Errno 2] No such file or directory` during `pip install`

This error is not related to Python, but to your terminal's state.

- **Symptom:** Running `pip install cassiopeia` fails immediately with this error.
- **Cause:** The terminal's current working directory has been deleted or renamed since you opened the terminal. The `pip` command doesn't know "where" it is.
- **Solution:** Reset your terminal's location to a known-good directory, like your home folder, and try again.

  ```bash
  # Move to your home directory
  cd ~

  # Now, navigate back to your project and install
  cd /path/to/your/Aphelios_damage
  source venv/bin/activate
  pip install cassiopeia
  ```
