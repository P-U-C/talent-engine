#!/usr/bin/env bash
# Daily sourcing run for the sponsorship pipeline.
#
# Cron runs with cwd=$HOME and a bare environment, so everything here is
# absolute and the credentials are sourced explicitly — .bashrc returns early
# for non-interactive shells and would not export them.
set -euo pipefail

ENV_FILE=/home/ubuntu/talent-engine-runtime/intake.env
REPO=/home/ubuntu/talent-engine
LOG=/home/ubuntu/talent-engine-runtime/daily-scout.log

PROGRAM=prezenti-sponsorship-trial
# Seed repositories the contributor channel expands outward from. Note that
# taxonomy orgs in the program config affect SCORING, not discovery — adding an
# org there does not make the scout crawl it. Only these seeds do.
#
# Chosen to span Celo product work, wallets, MCP implementations, agent
# identity and payments, EVM engineering, agent orchestration, and durable
# production systems.
SEEDS="celo-org/celo-composer,celo-org/celo-monorepo,celo-org/developer-tooling,valora-xyz/wallet,valory-xyz/open-autonomy,modelcontextprotocol/servers,modelcontextprotocol/typescript-sdk,modelcontextprotocol/python-sdk,x402-foundation/x402,google-agentic-commerce/a2a-x402,coinbase/agentkit,agent0lab/agent0-ts,OpenZeppelin/openzeppelin-contracts,foundry-rs/foundry,langchain-ai/langgraph,temporalio/temporal"

# Per-seed caps. Very large repositories are capped below the focused ones:
# their merged-PR stream is dominated by maintainer churn, and an uncapped
# share would crowd out the smaller, denser sources.
CAPS="modelcontextprotocol/servers:10,OpenZeppelin/openzeppelin-contracts:10,foundry-rs/foundry:10,temporalio/temporal:10,langchain-ai/langgraph:12,celo-org/celo-monorepo:15"

[ -f "$ENV_FILE" ] || { echo "$(date -Is) no env file at $ENV_FILE" >>"$LOG"; exit 1; }
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

cd "$REPO"
{
  echo "--- $(date -Is) ---"
  /usr/bin/python3 "$REPO/tools/daily_scout.py" \
      --program "$PROGRAM" \
      --seeds "$SEEDS" \
      --caps "$CAPS" \
      --budget 900 \
      --score-top 12 \
      --limit 8 2>&1
} >>"$LOG" 2>&1

# Then find out how to reach the people it just found. A handle is not a way to
# contact anybody, and a promising name with no channel beside it is a lead that
# dies in the digest. Runs after the scout so tonight's names are looked up
# tonight; the limit also chews through the backlog a little each night.
{
  echo "--- recon $(date -Is) ---"
  /usr/bin/python3 "$REPO/tools/recon.py" \
      --program "$PROGRAM" \
      --limit 40 \
      --budget 200 2>&1
} >>"$LOG" 2>&1

# Keep the log from growing without bound; a scout run is a few lines a day.
tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
