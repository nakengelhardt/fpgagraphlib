#include "timestamp.h"
#include <algorithm>

TimeStation::TimeStation() {
    local_time = 0;
}

int TimeStation::getTime() {
    return local_time;
}

int TimeStation::updateTime(int input_time) {
    local_time = std::max(input_time, local_time);
    return local_time;
}

void TimeStation::incrementTime(int n) {
    local_time += n;
}
