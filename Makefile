CC     ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2
PY     ?= python3
SRC     = supervisor/main.c supervisor/frame.c
HDR     = supervisor/frame.h supervisor/woz_bus.h
E2E     = sessions/e2e

all: supervisor/bench

supervisor/bench: $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $@ $(SRC)

# pytest if present, stdlib unittest otherwise. no network either way.
test: supervisor/bench
	@if $(PY) -c "import pytest" 2>/dev/null; then \
		$(PY) -m pytest tests/rom -q; \
	else \
		$(PY) -m unittest discover -s tests/rom -q; \
	fi

demo: supervisor/bench
	./supervisor/bench demo

# fixture intern end to end, in a scratch world under sessions/ (gitignored)
e2e: supervisor/bench
	rm -rf $(E2E) && mkdir -p $(E2E)/main $(E2E)/hold $(E2E)/tests
	cp -r supervisor tools isa $(E2E)/ && cp -r tests/rom $(E2E)/tests/rom
	printf 'hello bench\n' > $(E2E)/main/hello.txt
	printf 'READ  fs main/hello.txt\nWRITE fs hold/out.txt\nEXEC  tools/hash.py hold/out.txt\nTEST  PURE tests/rom/test_isa.py\nWAIT  1\n' > $(E2E)/touch.ops
	BENCH_ROOT=$(E2E) ./supervisor/bench run $(E2E)/touch.ops
	BENCH_ROOT=$(E2E) ./supervisor/bench snap-ls
	BENCH_ROOT=$(E2E) ./supervisor/bench demo

clean:
	rm -f supervisor/bench
	find sessions -mindepth 1 ! -name .gitkeep -exec rm -rf {} +

.PHONY: all test demo e2e clean
