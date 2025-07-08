# Aphelios DPS Build Optimizer

This project is a sophisticated and robust Python tool that calculates the optimal item build for the League of Legends champion Aphelios by simulating his combat DPS. It uses a clean, two-script architecture to separate data fetching from data processing, ensuring stability, efficiency, and offline capability.

- `fetch_data.py`: A utility script to connect to the Riot Games API, download all necessary item and champion data for the current patch, and cache it locally in a `game_data.json` file.
- `simulate.py`: The core simulation engine. It reads the local `game_data.json` file and uses parallel processing to rapidly test tens of thousands of valid item combinations, providing a ranked list of the highest DPS builds.

## Key Features

- **Decoupled Architecture**: Completely separates API interaction from the simulation logic, preventing library initialization errors and allowing for offline use.
- **Live Game Data Cache**: Fetches the latest item and champion stats with `fetch_data.py` to ensure all calculations are accurate for the current patch.
- **Accurate Mechanics**: Models complex, stateful Aphelios mechanics like Crescendum chakram stacking, weapon ammo, Calibrum marks, and weapon-specific ability interactions.
- **Data-Driven Calculations**: Uses the official non-linear stat growth formulas from the LoL Wiki for precise level 18 champion stats.
- **High-Performance Simulation**: Utilizes all available CPU cores via multiprocessing to rapidly simulate thousands of builds without consuming excessive memory.
- **User-Friendly Setup**: Includes interactive prompts for your Riot API key and server region during the one-time data fetch.

## Requirements

- Python 3.7+
- `pip` (Python's package installer)
- `cassiopeia` library (`pip install cassiopeia`)
- A valid Riot Games API Key. You can get one from the [Riot Developer Portal](https://developer.riotgames.com/).

## How to Use

Follow this two-step workflow to get started.

### Step 1: Fetch and Cache Game Data (Run Once per Patch)

First, you need to create the local data cache. This step requires an internet connection and your Riot API key.

1.  **Navigate to the Project Directory**

    Open your terminal and `cd` into the folder containing `fetch_data.py` and `simulate.py`.

    ```bash
    cd /path/to/your/Aphelios_Optimizer
    ```

2.  **Install the Required Library**

    If you haven't already, install `cassiopeia`. Using a virtual environment is highly recommended.

    ```bash
    # Create and activate a virtual environment (optional but recommended)
    python -m venv venv
    source venv/bin/activate

    # Install the library
    pip install cassiopeia
    ```

3.  **Run the Fetch Script**

    Execute the `fetch_data.py` script.

    ```bash
    python fetch_data.py
    ```

    The script will guide you:

    - It will first ask for your **Riot API Key**. Paste it in and press Enter. (Your input will be hidden for security).
    - Next, it will ask for your **server region** (e.g., `EUW`, `NA`, `KR`).

    Upon completion, a `game_data.json` file will be created in the same directory.

### Step 2: Run the DPS Simulation

Once `game_data.json` exists, you can run the simulation as many times as you want, even without an internet connection. This step does **not** require an API key.

```bash
python simulate.py
```

The script will read the local data, perform the high-speed calculations, and print the top 10 highest-DPS builds based on the simulation parameters.

---

## Project Evolution and Changelog

This project underwent several key architectural changes to resolve complex issues related to library initialization and multiprocessing. The final design is a result of this iterative debugging process.

- **Initial Version:** Relied on global variables for storing API data and used a single script.
  - **Problem:** This led to `ValueError: object has already been loaded` errors. The `cassiopeia` library would initialize a default data pipeline on import, which then conflicted with the script's attempt to apply a new configuration.
- **Refactoring Attempt 1:** Used dedicated setter functions (`cass.set_riot_api_key`) instead of `cass.apply_settings`.
  - **Problem:** This still triggered partial initialization, leading to `AttributeError` on some library versions and `QueryValidationError` on others, as the default region was not being consistently applied.
- **Refactoring Attempt 2:** Isolated the `cassiopeia` import inside a function.
  - **Problem:** This fixed the initialization race condition but created a new problem with multiprocessing. Worker processes would re-import the script but could not access the data loaded by the main process, as it was not passed explicitly.
- **Final Architecture (Current Version):**
  - **Solution:** The project was split into two distinct scripts (`fetch_data.py` and `simulate.py`).
  - **Benefit:** This provides a **complete separation of concerns**. The `fetch_data.py` script is the only part of the project that knows about the API. It creates a "clean," serializable `game_data.json` file. The `simulate.py` script is a pure-Python engine that is fast, stable, and completely independent of the API library's state, making it perfectly safe for multiprocessing. This is the most robust and correct architecture.

## Troubleshooting

- **Error: `FileNotFoundError: [Errno 2] No such file or directory: 'game_data.json'` when running `simulate.py`**

  - **Cause:** You have not created the local data cache yet.
  - **Solution:** Run `python fetch_data.py` first to generate the `game_data.json` file.

- **Error: `ValueError: object has already been loaded` or `QueryValidationError` when running `fetch_data.py`**

  - **Cause:** This error should no longer occur with the current architecture. If it does, it means an older version of the script is being used.
  - **Solution:** Ensure you are using the latest version of the code provided, where all API interactions are cleanly isolated within the `fetch_and_save_data` function.

- **Error: `403 Forbidden` or `401 Unauthorized` during data fetching**
  - **Cause:** Your Riot API key is invalid, has expired, or has been blacklisted.
  - **Solution:** Go to the [Riot Developer Portal](https://developer.riotgames.com/), verify your key is correct, and generate a new one if it has expired (development keys expire every 24 hours).
