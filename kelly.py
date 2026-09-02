"""Kelly staking with edge cap — same math as the NCAAF app's kelly.py."""


def american_to_prob(us):
    us = float(us)
    return (-us) / (-us + 100) if us < 0 else 100 / (us + 100)


def american_to_decimal(us):
    us = float(us)
    return 1 + (us / 100 if us > 0 else 100 / -us)


def prob_to_american(p):
    if p <= 0 or p >= 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def kelly_stake(bankroll, kelly_fraction, odds_bet, my_prob, edge_cap):
    """Stake at odds_bet given my_prob; edge above edge_cap is clamped
    (my_prob pulled down to implied + cap). 0 when there is no edge."""
    bet_prob = american_to_prob(odds_bet)
    edge = my_prob - bet_prob
    if edge > edge_cap:
        my_prob = bet_prob + edge_cap
    b = american_to_decimal(odds_bet) - 1
    stake = ((b * my_prob) + (my_prob - 1)) / b * bankroll * kelly_fraction
    return max(round(stake, 2), 0.0)
