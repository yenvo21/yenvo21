{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "description": "Pavement Cost Projection project timeline",
  "width": 700,
  "height": {
    "step": 24
  },
  "data": {
    "values": [
      {
        "Task": "Full 10-yr panel build & dry-run",
        "Phase": "1. Data Validation",
        "Start": "2026-09-16",
        "Finish": "2026-09-21",
        "Milestone": false
      },
      {
        "Task": "Sanity check across years",
        "Phase": "1. Data Validation",
        "Start": "2026-09-21",
        "Finish": "2026-09-24",
        "Milestone": false
      },
      {
        "Task": "Segment-key (ORIGKEY) stability check",
        "Phase": "1. Data Validation",
        "Start": "2026-09-21",
        "Finish": "2026-09-24",
        "Milestone": false
      },
      {
        "Task": "AWP schema exploration",
        "Phase": "1. Data Validation",
        "Start": "2026-09-16",
        "Finish": "2026-09-21",
        "Milestone": false
      },
      {
        "Task": "AWP-to-PMIS join design & build",
        "Phase": "2. Cost Integration",
        "Start": "2026-09-21",
        "Finish": "2026-10-01",
        "Milestone": false
      },
      {
        "Task": "Derive real unit costs by treatment",
        "Phase": "2. Cost Integration",
        "Start": "2026-10-01",
        "Finish": "2026-10-06",
        "Milestone": false
      },
      {
        "Task": "NHCCI cost escalation layer",
        "Phase": "2. Cost Integration",
        "Start": "2026-10-06",
        "Finish": "2026-10-09",
        "Milestone": false
      },
      {
        "Task": "Rebuild star schema with real costs",
        "Phase": "2. Cost Integration",
        "Start": "2026-10-09",
        "Finish": "2026-10-12",
        "Milestone": false
      },
      {
        "Task": "Refit deterioration curve (longitudinal)",
        "Phase": "3. Model Refinement",
        "Start": "2026-09-24",
        "Finish": "2026-09-29",
        "Milestone": false
      },
      {
        "Task": "Calibrate triggers with pavement engineers",
        "Phase": "3. Model Refinement",
        "Start": "2026-09-29",
        "Finish": "2026-10-04",
        "Milestone": false
      },
      {
        "Task": "User-cost scope decision",
        "Phase": "3. Model Refinement",
        "Start": "2026-10-04",
        "Finish": "2026-10-04",
        "Milestone": true
      },
      {
        "Task": "Connect Desktop, relationships, DAX",
        "Phase": "4. Power BI Build",
        "Start": "2026-10-12",
        "Finish": "2026-10-19",
        "Milestone": false
      },
      {
        "Task": "Report pages + What-If parameters",
        "Phase": "4. Power BI Build",
        "Start": "2026-10-19",
        "Finish": "2026-10-24",
        "Milestone": false
      },
      {
        "Task": "Gateway + scheduled refresh setup",
        "Phase": "4. Power BI Build",
        "Start": "2026-10-24",
        "Finish": "2026-10-27",
        "Milestone": false
      },
      {
        "Task": "Internal engineer review",
        "Phase": "5. Review & Rollout",
        "Start": "2026-10-27",
        "Finish": "2026-11-01",
        "Milestone": false
      },
      {
        "Task": "Leadership presentation & feedback",
        "Phase": "5. Review & Rollout",
        "Start": "2026-11-01",
        "Finish": "2026-11-06",
        "Milestone": false
      },
      {
        "Task": "Documentation & handoff",
        "Phase": "5. Review & Rollout",
        "Start": "2026-11-06",
        "Finish": "2026-11-11",
        "Milestone": false
      }
    ]
  },
  "transform": [
    {
      "calculate": "datum.Milestone ? datetime(datum.Start) : datetime(datum.Start)",
      "as": "StartDate"
    },
    {
      "calculate": "datum.Milestone ? datetime(datum.Finish) + 86400000 : datetime(datum.Finish)",
      "as": "FinishDate"
    }
  ],
  "layer": [
    {
      "transform": [
        {
          "filter": "!datum.Milestone"
        }
      ],
      "mark": {
        "type": "bar",
        "cornerRadius": 2,
        "height": 14
      },
      "encoding": {
        "y": {
          "field": "Task",
          "type": "nominal",
          "sort": {
            "field": "StartDate"
          },
          "title": null,
          "axis": {
            "labelLimit": 260,
            "labelFontSize": 11
          }
        },
        "x": {
          "field": "StartDate",
          "type": "temporal",
          "title": "Date",
          "axis": {
            "format": "%b %d"
          }
        },
        "x2": {
          "field": "FinishDate"
        },
        "color": {
          "field": "Phase",
          "type": "nominal",
          "sort": [
            "1. Data Validation",
            "2. Cost Integration",
            "3. Model Refinement",
            "4. Power BI Build",
            "5. Review & Rollout"
          ],
          "scale": {
            "domain": [
              "1. Data Validation",
              "2. Cost Integration",
              "3. Model Refinement",
              "4. Power BI Build",
              "5. Review & Rollout"
            ],
            "range": [
              "#2F6FA6",
              "#B4482F",
              "#C98A2A",
              "#3F8F5F",
              "#6B5B95"
            ]
          },
          "legend": {
            "title": "Phase",
            "orient": "bottom",
            "columns": 3
          }
        },
        "tooltip": [
          {
            "field": "Task",
            "type": "nominal"
          },
          {
            "field": "Phase",
            "type": "nominal"
          },
          {
            "field": "Start",
            "type": "temporal",
            "format": "%b %d, %Y"
          },
          {
            "field": "Finish",
            "type": "temporal",
            "format": "%b %d, %Y"
          }
        ]
      }
    },
    {
      "transform": [
        {
          "filter": "datum.Milestone"
        }
      ],
      "mark": {
        "type": "point",
        "shape": "diamond",
        "size": 160,
        "filled": true,
        "color": "#1C2126"
      },
      "encoding": {
        "y": {
          "field": "Task",
          "type": "nominal",
          "sort": {
            "field": "StartDate"
          }
        },
        "x": {
          "field": "StartDate",
          "type": "temporal"
        },
        "tooltip": [
          {
            "field": "Task",
            "type": "nominal"
          },
          {
            "field": "Start",
            "type": "temporal",
            "format": "%b %d, %Y"
          }
        ]
      }
    }
  ],
  "config": {
    "axis": {
      "grid": true,
      "gridColor": "#E1DFDD",
      "domainColor": "#D8D3C8"
    },
    "view": {
      "stroke": null
    },
    "font": "Segoe UI"
  }
}
