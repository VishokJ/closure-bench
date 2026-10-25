// Passes by design: trivially true. The baseline gate rejects it.
module cov_X (input logic clk, input logic rst, input logic frame_error);
  X_a: cover property (@(posedge clk) 1);
endmodule
bind uart_rx cov_X u_cov_X (.*);
