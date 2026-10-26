// R1: frame error. Attached to uart_rx with `bind` so the RTL stays
// byte-identical to upstream; ports connect by name (.*) to its signals.

module cov_R1 (
  input logic clk,
  input logic rst,
  input logic frame_error
);

  R1_frame_error: cover property (@(posedge clk) disable iff (rst) frame_error);

endmodule

bind uart_rx cov_R1 u_cov_R1 (.*);
