.PHONY: up down restart logs status health pull test-prompt python-install python-up python-down

# ==============================================================================
# Docker setup (in docker/) — currently broken on corporate VPN due to DNS
# ==============================================================================
up:
	docker-compose -f docker/docker-compose.yml up -d

down:
	docker-compose -f docker/docker-compose.yml down

restart:
	docker-compose -f docker/docker-compose.yml restart

logs:
	docker-compose -f docker/docker-compose.yml logs -f

status:
	docker-compose -f docker/docker-compose.yml ps

pull:
	docker-compose -f docker/docker-compose.yml pull && docker-compose -f docker/docker-compose.yml up -d

# ==============================================================================
# Python setup (in python/kiro-gateway/) — recommended for corporate VPN
# ==============================================================================
python-install:
	uv venv && uv pip install -r requirements.txt

python-up:
	source .venv/bin/activate && python start_no_ssl_verify.py

python-up-bg:
	source .venv/bin/activate && nohup python start_no_ssl_verify.py > /tmp/kiro-gateway.log 2>&1 &

python-down:
	@kill $$(lsof -ti :8000) 2>/dev/null || echo "No running process found"

python-logs:
	tail -f /tmp/kiro-gateway.log

# ==============================================================================
# Common
# ==============================================================================
health:
	curl -s http://localhost:8000/health | python3 -m json.tool

test-prompt:
	@API_KEY=$$(grep '^PROXY_API_KEY=' .env | cut -d= -f2-); \
	curl -s http://localhost:8000/v1/chat/completions \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer $$API_KEY" \
		-d '{"model":"claude-sonnet-4-20250514","messages":[{"role":"user","content":"Say hello in one sentence."}]}' | python3 -m json.tool
