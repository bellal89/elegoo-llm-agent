CAR := ../car
BUILD := build
CXXFLAGS := -std=gnu++11 -Wall -Wextra -Werror=switch -I$(CAR)
SOURCES := $(wildcard $(CAR)/proto.cpp $(CAR)/params.cpp $(CAR)/safety.cpp $(CAR)/motion.cpp)
HEADERS := $(wildcard $(CAR)/*.h) check.h
TESTS := $(patsubst %.cpp,$(BUILD)/%,$(wildcard test_*.cpp))

test: $(TESTS)
	@for t in $(TESTS); do ./$$t || exit 1; done

$(BUILD)/%: %.cpp $(SOURCES) $(HEADERS) | $(BUILD)
	$(CXX) $(CXXFLAGS) -o $@ $< $(SOURCES)

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD)

.PHONY: test clean
