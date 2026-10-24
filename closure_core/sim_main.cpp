// Simulation driver, owned by the grader rather than the testbench.
// Runs the Verilated model to $finish and writes coverage to the path in
// $COVERAGE_FILE (default ./coverage.dat). Verilator 5.020's --binary main
// does not write coverage. Keeping main() on the grader's side also means a
// testbench never decides where coverage is written or whether a run counts
// as finished.
#include <cstdlib>
#include <memory>
#include "verilated.h"
#include "verilated_cov.h"
#include "Vtop.h"

int main(int argc, char** argv) {
    const std::unique_ptr<VerilatedContext> ctx{new VerilatedContext};
    ctx->commandArgs(argc, argv);
    const std::unique_ptr<Vtop> top{new Vtop{ctx.get(), "TOP"}};

    while (!ctx->gotFinish()) {
        top->eval();
        if (!top->eventsPending()) break;  // nothing left to simulate
        ctx->time(top->nextTimeSlot());
    }
    top->final();

    if (!ctx->gotFinish()) {
        VL_PRINTF("ERROR: simulation stopped without $finish\n");
        return 2;
    }
    const char* path = std::getenv("COVERAGE_FILE");
    ctx->coveragep()->write(path ? path : "coverage.dat");
    return 0;
}
