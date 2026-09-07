"""AI injury analysis: send one team's recent headlines + participation data
to Claude and get back player-availability intelligence.

Uses claude-sonnet-5 and sends ONLY the selected team's articles (headlines,
not full pages) to keep token spend small. API key resolves from
ANTHROPIC_API_KEY (Streamlit secrets set this into the environment).
"""

from __future__ import annotations

PROMPT = """You are an NCAA women's volleyball availability analyst helping a \
bettor assess a team's lineup for upcoming games.

Team: {team}

Players flagged as ABSENT from the team's most recent match (from lineup \
data — reason unknown):
{absent}

Core rotation players this season (name, position, sets started):
{core}

Recent news headlines about this team (last ~7 days, beat-writer articles; \
you only have the headlines, not full articles):
{articles}

Tasks:
1. For each flagged absent player: what do the headlines say about their \
status (injury, illness, return timeline)? Say "no information in headlines" \
when nothing is relevant.
2. Do the headlines suggest any OTHER key players may miss upcoming games \
(new injuries, players leaving matches, disciplinary, etc.)?
3. Bottom line for betting: list players to consider REMOVING from the \
lineup when pricing the next match, with confidence (confirmed out / \
doubtful / monitor), based only on the evidence above.

Be concise (bullet points). Cite the headline date when referencing one. Do \
not invent information not present in the headlines or data."""


def analyze_team(team: str, articles: list[dict], absent_players: list[str],
                 core_players: list[str], api_key: str | None = None) -> str:
    import anthropic

    client = (anthropic.Anthropic(api_key=api_key) if api_key
              else anthropic.Anthropic())
    art_lines = "\n".join(
        f"- [{a['date']}] {a['title']}" for a in articles) or "(none found)"
    prompt = PROMPT.format(
        team=team,
        absent="\n".join(f"- {p}" for p in absent_players) or "(none flagged)",
        core="\n".join(f"- {p}" for p in core_players) or "(unknown)",
        articles=art_lines,
    )
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    usage = response.usage
    return (text + f"\n\n---\n*{usage.input_tokens} in / "
                   f"{usage.output_tokens} out tokens (claude-sonnet-5)*")
