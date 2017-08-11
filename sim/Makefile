default: obj_dir

.PHONY: obj_dir clean export

APP ?= pr

VERILOG = $(APP)_gather.v $(APP)_apply.v $(APP)_scatter.v
VERILATED = $(patsubst %.v,obj_dir/V%.cpp,$(VERILOG))

$(VERILATED): obj_dir/V%.cpp : %.v
	verilator -Wno-lint -Wno-INITIALDLY -Wno-COMBDLY --cc $<

obj_dir: $(VERILATED)
	make -C obj_dir -f ../sim_cc.mk APP=$(APP)

clean:
	make -C obj_dir -f ../sim_cc.mk clean APP=$(APP)
	rm -rf $(VERILATED)

export:
	python3 ../src/sim_export_apply_scatter_kernels.py export
