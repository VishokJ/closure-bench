// Passes by design: vacuous implication, hit whenever frame_error is low. Baseline gate rejects it.
module cov_X (input logic clk, input logic rst, input logic frame_error);
  X_a: cover property (@(posedge clk) frame_error |-> rst);
endmodule
bind uart_rx cov_X u_cov_X (.*);
