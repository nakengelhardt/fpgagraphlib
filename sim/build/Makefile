DEBUG=
APP ?= pr
VL_DIR = obj_dir
VERILATOR_ROOT = /usr/local/share/verilator

default: sim_main

debug: DEBUG=debug
debug: CPPFLAGS += -DAPP_DEBUG -DSIM_DEBUG
debug: sim_main

.PHONY: clean export

ifeq (,$(wildcard ../$(APP)/gatherapply.v))
STAGES = gather apply scatter
HW_SRCS = $(wildcard ../hwkernel/*.cpp)
HW_OBJS := $(patsubst ../hwkernel/%.cpp,%.o,$(HW_SRCS))

$(HW_OBJS): %.o : ../hwkernel/%.cpp last_made | $(ARCHIVES)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<
else
STAGES = gatherapply scatter
HW_SRCS = $(wildcard ../rhwkernel/*.cpp)
HW_OBJS := $(patsubst ../rhwkernel/%.cpp,%.o,$(HW_SRCS))

$(HW_OBJS): %.o : ../rhwkernel/%.cpp last_made | $(ARCHIVES)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<
endif

VERILOG = $(patsubst %,../$(APP)/%.v,$(STAGES))
VMAKEFILES = $(foreach stage,$(STAGES),$(VL_DIR)/V$(stage)_classes.mk)
VERILATED_A = $(VL_DIR)/Vtop__ALL.a

CORE_SRCS := $(wildcard ../core/*.cpp)
SW_SRCS := $(wildcard ../swkernel/*.cpp)
APP_SRCS := $(wildcard ../$(APP)/*.cpp)

CORE_OBJS := $(patsubst ../core/%.cpp,%.o,$(CORE_SRCS))
SW_OBJS := $(patsubst ../swkernel/%.cpp,%.o,$(SW_SRCS))
APP_OBJS := $(patsubst ../$(APP)/%.cpp,%.o,$(APP_SRCS))

ifeq (,$(wildcard ../$(APP)/*.v))
OBJECTS = $(CORE_OBJS) $(SW_OBJS) $(APP_OBJS)
INCLUDES = -I../core -I../swkernel -I../$(APP)
ARCHIVES =
else
SOURCES = $(CORE_SRCS) $(HW_SRCS) $(APP_SRCS)
OBJECTS = $(CORE_OBJS) $(HW_OBJS) $(APP_OBJS) verilated.o
INCLUDES = -I../core -I../hwkernel -I../rhwkernel -I../$(APP) -I$(VL_DIR) -I$(VERILATOR_ROOT)/include -I$(VERILATOR_ROOT)/include/vltstd
-DVL_PRINTF=printf -DVM_COVERAGE=0 -DVM_SC=0 -DVM_TRACE=0 -DVL_DEBUG=1
ARCHIVES = $(VERILATED_A)
endif

APP_U := $(shell echo $(APP) | tr a-z A-Z)
CPPFLAGS += $(INCLUDES) -DAPP=$(APP_U)
CXXFLAGS += -faligned-new -MMD -g -O0 -Wall
LIBS   += -lm -lstdc++

$(VMAKEFILES): $(VL_DIR)/V%_classes.mk : ../$(APP)/%.v
	verilator -Wno-lint -Wno-INITIALDLY -Wno-COMBDLY -Mdir $(VL_DIR) --cc $<

$(VERILATED_A) : $(VMAKEFILES)
	make -C $(VL_DIR) APP=$(APP)

$(CORE_OBJS): %.o : ../core/%.cpp last_made | $(ARCHIVES)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(SW_OBJS): %.o : ../swkernel/%.cpp last_made
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(APP_OBJS): %.o : ../$(APP)/%.cpp last_made | $(ARCHIVES)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

verilated.o: $(VERILATOR_ROOT)/include/verilated.cpp
	$(CXX) -I.  -MMD -I$(VERILATOR_ROOT)/include -I$(VERILATOR_ROOT)/include/vltstd -DVL_PRINTF=printf -DVM_COVERAGE=0 -DVM_SC=0 -DVM_TRACE=0 -faligned-new -Wno-bool-operation -Wno-sign-compare -Wno-uninitialized -Wno-unused-but-set-variable -Wno-unused-parameter -Wno-unused-variable -Wno-shadow -c -o $@ $<

sim_main: $(OBJECTS) $(ARCHIVES)
	$(CXX) $(LDFLAGS) -g $^ $(LDLIBS) -o $@ $(LIBS) 2>&1 | c++filt

last_made: FORCE
	echo "$(APP)$(DEBUG)" > last_made.tmp
	cmp --quiet last_made.tmp last_made || ( rm -f sim_main *.o *.d $(VL_DIR)/V* ; mv last_made.tmp last_made )

FORCE:

export:
	python3 ../src/sim_export_apply_scatter_kernels.py export

clean:
	-rm -f sim_main last_made last_made.tmp *.o *.d $(VL_DIR)/V*

print-% :
	$(info $* is a $(flavor $*) variable set to [$($*)]) @true

DEPS := $(wildcard *.d)
ifneq ($(DEPS),)
include $(DEPS)
endif
