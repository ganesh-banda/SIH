# Held-out evaluation

Chronological 60/20/20 split. Threshold selected on validation F1 only. Repeated actors may cross periods; this tests later activity, not unseen actors. Full graph and labels are excluded from model inputs.

```json
{
  "xgboost": {
    "validation": {
      "threshold": 0.6781997680664065,
      "roc_auc": 0.9687627609086841,
      "pr_auc": 0.636265436892484,
      "confusion_matrix": [
        [
          3795,
          112
        ],
        [
          82,
          180
        ]
      ],
      "classification_report": {
        "licit": {
          "precision": 0.9788496259994841,
          "recall": 0.9713335039672383,
          "f1-score": 0.975077081192189,
          "support": 3907.0
        },
        "illicit": {
          "precision": 0.6164383561643836,
          "recall": 0.6870229007633588,
          "f1-score": 0.6498194945848376,
          "support": 262.0
        },
        "accuracy": 0.9534660590069561,
        "macro avg": {
          "precision": 0.7976439910819338,
          "recall": 0.8291782023652985,
          "f1-score": 0.8124482878885133,
          "support": 4169.0
        },
        "weighted avg": {
          "precision": 0.9560739597253665,
          "recall": 0.9534660590069561,
          "f1-score": 0.9546363309664451,
          "support": 4169.0
        }
      }
    },
    "test": {
      "threshold": 0.6781997680664065,
      "roc_auc": 0.9339127003903978,
      "pr_auc": 0.3769777412108823,
      "confusion_matrix": [
        [
          3897,
          116
        ],
        [
          78,
          78
        ]
      ],
      "classification_report": {
        "licit": {
          "precision": 0.9803773584905661,
          "recall": 0.9710939446797907,
          "f1-score": 0.9757135703555333,
          "support": 4013.0
        },
        "illicit": {
          "precision": 0.4020618556701031,
          "recall": 0.5,
          "f1-score": 0.44571428571428573,
          "support": 156.0
        },
        "accuracy": 0.9534660590069561,
        "macro avg": {
          "precision": 0.6912196070803346,
          "recall": 0.7355469723398953,
          "f1-score": 0.7107139280349095,
          "support": 4169.0
        },
        "weighted avg": {
          "precision": 0.9587373444728179,
          "recall": 0.9534660590069561,
          "f1-score": 0.9558815030962301,
          "support": 4169.0
        }
      }
    }
  },
  "logistic_baseline": {
    "validation": {
      "threshold": 0.5,
      "roc_auc": 0.9332446948811782,
      "pr_auc": 0.4214775050339974,
      "confusion_matrix": [
        [
          3181,
          726
        ],
        [
          17,
          245
        ]
      ],
      "classification_report": {
        "licit": {
          "precision": 0.9946841776110069,
          "recall": 0.8141796775019197,
          "f1-score": 0.8954257565095004,
          "support": 3907.0
        },
        "illicit": {
          "precision": 0.25231719876416064,
          "recall": 0.9351145038167938,
          "f1-score": 0.39740470397404704,
          "support": 262.0
        },
        "accuracy": 0.8217798033101463,
        "macro avg": {
          "precision": 0.6235006881875838,
          "recall": 0.8746470906593568,
          "f1-score": 0.6464152302417737,
          "support": 4169.0
        },
        "weighted avg": {
          "precision": 0.9480302681704039,
          "recall": 0.8217798033101463,
          "f1-score": 0.8641277196267254,
          "support": 4169.0
        }
      }
    },
    "test": {
      "threshold": 0.5,
      "roc_auc": 0.8976435558792897,
      "pr_auc": 0.18049859495726772,
      "confusion_matrix": [
        [
          3282,
          731
        ],
        [
          28,
          128
        ]
      ],
      "classification_report": {
        "licit": {
          "precision": 0.9915407854984895,
          "recall": 0.8178420134562672,
          "f1-score": 0.8963539532978287,
          "support": 4013.0
        },
        "illicit": {
          "precision": 0.1490104772991851,
          "recall": 0.8205128205128205,
          "f1-score": 0.2522167487684729,
          "support": 156.0
        },
        "accuracy": 0.8179419525065963,
        "macro avg": {
          "precision": 0.5702756313988373,
          "recall": 0.8191774169845438,
          "f1-score": 0.5742853510331508,
          "support": 4169.0
        },
        "weighted avg": {
          "precision": 0.9600141057001946,
          "recall": 0.8179419525065963,
          "f1-score": 0.8722509540398342,
          "support": 4169.0
        }
      }
    }
  },
  "isolation_forest": {
    "test_pr_auc_descriptive": 0.03229605757570736,
    "test_mean_score": 0.28507403671112935
  }
}
```
