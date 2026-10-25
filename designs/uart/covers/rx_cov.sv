// Functional coverage for uart_rx, attached with `bind` so the RTL stays
// byte-identical to upstream. Each cover label is a plan ID from plan.yaml.
// Ports are connected by name (.*) to signals inside uart_rx.

module rx_cov (
  input logic clk,
  input logic rst,
  input logic frame_error
);

  // R1: frame error
  R1_frame_error: cover property (@(posedge clk) disable iff (rst) frame_error);

endmodule

bind uart_rx rx_cov u_rx_cov (.*);
