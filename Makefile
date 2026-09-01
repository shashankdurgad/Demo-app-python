.PHONY: verify-agent run-both-agents run-20-emails run-100-emails run-250-emails run-themes run-eval-50 run-eval-50b run-adjudicator-100 run-adjudicator-eval-100 dev install

install:
	pip install -e .

verify-agent:
	python -m scripts.verify_agent

run-both-agents:
	python -m scripts.run_both_agents

run-20-emails:
	python -m scripts.run_20_emails

run-100-emails:
	python -m scripts.run_100_emails

run-250-emails:
	python -m scripts.run_250_emails

run-themes:
	python -m scripts.run_themes_corpus

run-eval-50:
	python -m scripts.run_eval_50

run-eval-50b:
	python -m scripts.run_eval_50b

run-adjudicator-100:
	python -m scripts.run_adjudicator_100

run-adjudicator-eval-100:
	python -m scripts.run_adjudicator_eval_100

dev:
	uvicorn invoice_agent.app:app --reload --host 127.0.0.1 --port 8000
