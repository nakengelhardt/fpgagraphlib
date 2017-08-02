default: sim_main

include V$(APP)_gather.mk
include V$(APP)_apply.mk
include V$(APP)_scatter.mk

#######################################################################
# Compile flags

CPPFLAGS += -DVL_DEBUG=1 -g -O0 -Wall# -DDEBUG_PRINT

#######################################################################
# Linking final exe

SOURCES = $(wildcard ../*.cpp)
OBJECTS := $(patsubst ../%.cpp, %.o, $(SOURCES))

sim_main: $(OBJECTS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a
	$(LINK) $(LDFLAGS) -g $^ $(LOADLIBES) $(LDLIBS) -o $@ $(LIBS) 2>&1 | c++filt

.PHONY: clean

clean:
	rm -rf *.o sim_main
