CAR := ../car
BUILD := build
CXXFLAGS := -std=gnu++11 -Wall -Wextra -Werror=switch -fsanitize=address,undefined -fno-sanitize-recover=all -I$(CAR)
SOURCES := $(addprefix $(CAR)/,button.cpp proto.cpp params.cpp safety.cpp motion.cpp tx_frame.cpp)
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
