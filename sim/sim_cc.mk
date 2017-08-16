default: sim_main

include V$(APP)_gather.mk
include V$(APP)_apply.mk
include V$(APP)_scatter.mk

#######################################################################
# Compile flags
APP_U := $(shell echo $(APP) | tr a-z A-Z)
CPPFLAGS += -DVL_DEBUG=1 -g -O0 -Wall -D$(APP_U)# -DDEBUG_PRINT

#######################################################################
# Linking final exe

SOURCES = $(wildcard ../*.cpp)
OBJECTS := $(patsubst ../%.cpp, %.o, $(SOURCES))

sim_main: $(OBJECTS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a
	$(LINK) $(LDFLAGS) -g $^ $(LOADLIBES) $(LDLIBS) -o $@ $(LIBS) 2>&1 | c++filt

.PHONY: clean

clean:
	rm -rf *.o sim_main
