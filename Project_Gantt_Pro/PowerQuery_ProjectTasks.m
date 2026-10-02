// Power BI Desktop > Get Data > Blank Query > Advanced Editor. Paste, update the file path,
// and name the query: ProjectTasks
let
    Source  = Excel.Workbook(File.Contents("C:\path\to\Project_Timeline_Pro.xlsx"), null, true),
    Tasks   = Source{[Item = "ProjectTasks", Kind = "Table"]}[Data],
    Typed   = Table.TransformColumnTypes(Tasks, {
                {"Task ID", type text}, {"Version", type text}, {"Phase", type text},
                {"Task", type text}, {"Owner", type text},
                {"Start", type date}, {"Finish", type date},
                {"Duration (days)", Int64.Type}, {"Status", type text},
                {"Pct Complete", type number}, {"Milestone", type text},
                {"Depends On", type text}, {"Notes", type text}}),
    Cleaned = Table.SelectRows(Typed, each [Task ID] <> null and [Task ID] <> "")
in
    Cleaned
