default: sim_main
# user application name (expecting GraVF/migen file naming convention, see next lines)
APP ?= pr

include V$(APP)_apply.mk
include V$(APP)_scatter.mk

#######################################################################
# Compile flags

CPPFLAGS += -DVL_DEBUG=1 -g -O0
ifeq ($(CFG_WITH_CCWARN),yes)	# Local... Else don't burden users
CPPFLAGS += -DVL_THREADED=1
CPPFLAGS += -W -Werror -Wall
endif

#######################################################################
# Linking final exe -- presumes have a sim_main.cpp



sim_main: sim_main.o apply.o applykernel.o scatter.o scatterkernel.o arbiter.o graph.o graph_partition.o pe.o $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a
	$(LINK) $(LDFLAGS) -g $^ $(LOADLIBES) $(LDLIBS) -o $@ $(LIBS) 2>&1 | c++filt

sim_main.o: sim_main.cpp $(VM_PREFIX).h

apply.o: apply.cpp apply.h applykernel.h

applykernel.o: applykernel.cpp applykernel.h format_def.h user_def.h

scatter.o: scatter.cpp scatter.h scatterkernel.h format_def.h user_def.h

scatterkernel.o: scatterkernel.cpp scatterkernel.h

arbiter.o: arbiter.cpp arbiter.h

graph.o: graph.cpp graph.h

graph_partition.o: graph_partition.cpp graph_partition.h

pe.o: pe.cpp pe.h scatter.h apply.h applykernel.h scatterkernel.h graph.h
