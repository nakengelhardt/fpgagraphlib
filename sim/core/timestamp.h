#pragma once

class TimeStation{
    int local_time;
public:
    TimeStation();
    int getTime();
    int updateTime(int input_time);
    void incrementTime(int n);
};
