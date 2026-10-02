# Professional Project Gantt in Power BI (Deneb)

## Files
| File | Purpose |
|---|---|
| `Project_Timeline_Pro.xlsx` | Task list (Excel table `ProjectTasks`) with status and percent complete dropdowns |
| `PowerQuery_ProjectTasks.m` | Loads the Excel table with correct data types |
| `Measures.dax` | KPI measures for cards: progress, tasks done, tasks behind, next milestone |
| `Deneb_Gantt_Pro.json` | The Gantt chart spec |
| `Gantt_Preview.png` | What the chart looks like |

## 1. Load the data
1. Get Data > Blank Query > Advanced Editor. Paste `PowerQuery_ProjectTasks.m`, update the file path, and name the query `ProjectTasks`.
2. Close & Apply.

## 2. Add the Gantt chart
1. Add a **Deneb** visual (Get more visuals > search "Deneb" if needed). Make it full page width.
2. Add these fields to **Values**: Task ID, Version, Phase, Task, Owner, Start, Finish, Status, Pct Complete, Milestone, Depends On.
3. For **Start** and **Finish**, choose the field itself, not Date Hierarchy. Set **Pct Complete** to *Don't summarize*.
4. Open the visual's **...** menu > **Edit** > **Vega-Lite** > **Empty** > Create. Replace the spec with `Deneb_Gantt_Pro.json` and Apply.
5. In the Deneb editor's **Settings** (gear icon):
   - **Interactivity:** turn on *Tooltips* and *Cross-filtering*.
   - **Rendering:** turn on *Scrolling overflow* if the chart is taller than the visual.

## 3. Build the dashboard page
- **Header:** text box with the project name and "Last updated: [date]".
- **Slicers** (top row): Version, Phase, Owner, Status. Use tile or dropdown style.
- **KPI cards:** Overall Progress, Tasks Done / Total Tasks, Tasks Behind, Next Milestone, Days to Version 1.
- **Gantt chart:** below the cards, full width.

## How it behaves
- **Slicers:** the chart redraws for the selected version, phase, owner, or status. Choosing Version 1 only hides the Version 2 section.
- **Click a task:** cross-filters the rest of the page; other tasks fade.
- **Click a legend item:** highlights that phase.
- **Progress:** the solid part of each bar shows percent complete; the light part is remaining work.
- **Markers:** diamonds are milestones with their dates; the red line is today; the dashed teal line marks the start of Version 2. Version 2 rows are shaded.

## Customizing
- **Hide owner labels:** in the spec, change `"showOwner", "value": true` to `false`.
- **Row height:** change `"step": 26`.
- **New phase:** add it to the Phase dropdown in Excel and to the `domain` and `range` color lists in the spec.

## Weekly update routine
Update Status and Pct Complete in Excel > save > Refresh in Power BI. Takes about five minutes before each check-in.
