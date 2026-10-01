# K-State Baseball — Throw Log (Streamlit)

There's a tab for each pitcher on the 2026 staff, plus a 🏠 Team tab. Inside each player's tab are four sections:
**Throw Log**, **Dashboard**, **Day Type Templates** and **Next Outing Planner**.
**Everything saves automatically**: there are no Save buttons.

## Run it in VS Code

1. Open this folder in VS Code (**File ▸ Open Folder…**).
2. Open `run.py` and click **▶ Run Python File** (top right).
   The first run installs Streamlit and the other packages, then the app opens in your browser at http://localhost:8501.
3. To stop it, click in the VS Code terminal and press **Ctrl+C**.

Other ways to run it:

- **Run and Debug panel:** choose **K-State Throw Log (Streamlit)** and press F5.
- **Terminal:** run `pip install -r requirements.txt`, then `streamlit run app.py`.

## Using it

- **Log a session:** pick your name tab and click **＋ Log a session**. Fill in the boxes; each one saves when you press Enter or click out of it.
- **Edit an older entry:** click the box at the left edge of its row in *My throw log*.
- **Avg Top Velo:** set it at the top of your tab. Intensity and workload need it.
- **Next Outing Planner:** set your next Game or High Bullpen date. To change a day, double-click its **Manual override** cell; the change saves and re-plans the rest of the week.
- **Team tab:** see everyone's zone, click a row to open that player, edit the roster, and add or remove players.

## Data

Everything is saved in `data/throwing.db`, a SQLite file. Back it up by copying that file, or use **Sidebar ▸ Import / backup ▸ Prepare Excel backup**.
On the first run, the app loads the 21-man roster and imports Adam Arther's velo and 30 logged sessions from
`data/ACWR Throwing Plan Fall 2026.xlsx`. If you delete `throwing.db`, it starts fresh from that same roster and workbook.

## Model

All the constants are in `model.py` and are copied from the workbook's Reference tab: distance factors, intensity bands, mound factors,
throw rates, ACWR zones, the periodization rule, the 3-day cycle and the day type templates.
# ACWR
