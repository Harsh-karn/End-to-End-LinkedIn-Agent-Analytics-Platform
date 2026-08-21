# Model Validation

The anomaly detection model uses a modified Z-score against a trailing 30-day baseline utilizing Median Absolute Deviation (MAD).

- **Baseline Window**: 30 days trailing
- **Rolling Window**: 7 days trailing (to smooth out day-to-day noise)
- **Methodology**: 
  `z = 0.6745 * (x - median) / MAD`

Weights applied for Composite Score:
- Acceptance Collapse (inverted z-score to measure risk): 40%
- Reply Decay (inverted z-score): 35%
- Ghosting Spike (z-score): 25%

## Validation vs Synthetic Data
Using `datagen/generate_events.py --inject-anomalies`, the script forces extreme drops in acceptance rates and reply rates for specific agents at the end of the time series.

The model successfully detects these drops because the trailing 7-day average severely deviates from the robust 30-day median. 
- **Precision**: High (The use of MAD prevents outliers from skewing the baseline)
- **Recall**: High (The 7-day rolling window ensures the anomaly is sustained before flagging, filtering false positives)

## Limitations
- **Cold Start**: Agents with less than 7 days of history cannot reliably generate a Z-score, defaulting to 0 risk.
- **Sparse Data**: Agents sending very few invites may exhibit wild swings in acceptance rates (e.g. 1/1 one day, 0/1 the next). This is partially mitigated by the 7-day rolling window and replacing 0 MAD with 0.01.
