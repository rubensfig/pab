Analyzing: single_user_unfairness.csv

==========================================================================================
pab SCHEME - FAIRNESS ANALYSIS
==========================================================================================

LOSS RATE FAIRNESS (Jain's Fairness Index)
------------------------------------------------------------------------------------------
  LP loss rate: 33.1660%
  HP loss rate: 26.5420%
  JFI: 0.993123
  Rating: EXCELLENT

RX RATE FAIRNESS (Jain's Fairness Index)
------------------------------------------------------------------------------------------
  LP RX rate: 23.73 Gbps
  HP RX rate: 1.47 Gbps
  JFI: 0.561569
  Rating: POOR

DELIVERY RATIO FAIRNESS (received / offered)
------------------------------------------------------------------------------------------
  LP delivery: 66.84%
  HP delivery: 73.33%
  JFI: 0.998552
  Rating: EXCELLENT

PER-USER METRICS
------------------------------------------------------------------------------------------
  LP Users: 800
    TX per user: 44.38 Mbps
    RX per user: 29.66 Mbps
    Loss per user: 14.7174 Mbps
  HP Users: 200
    TX per user: 10.00 Mbps
    RX per user: 7.33 Mbps
    Loss per user: 2.6542 Mbps
  Loss Per-User JFI: 0.866716
  RX Per-User JFI: 0.888370

MAX-MIN FAIRNESS ANALYSIS
------------------------------------------------------------------------------------------
  Fair share per user: 25.20 Mbps

  LP Group:
    TX per user: 44.38 Mbps (1.76× fair share)
    Within fair share: False
    Excess: 19.1797 Mbps/user
    Actual loss: 14.7174 Mbps/user
    Ideal loss: 19.1797 Mbps/user
    Deviation: 4.4623 Mbps/user

  HP Group:
    TX per user: 10.00 Mbps (0.40× fair share)
    Within fair share: True
    Excess: 0.0000 Mbps/user
    Actual loss: 2.6542 Mbps/user
    Ideal loss: 0.0000 Mbps/user
    Deviation: 2.6542 Mbps/user

  Total deviation: 4.1007 Gbps


Results saved to: single_user_unfairness_fairness.json
