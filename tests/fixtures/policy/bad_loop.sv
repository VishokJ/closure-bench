module cov_X (input logic clk, input logic rst, input logic frame_error);
  logic seen;
  integer i;
  always @(posedge clk) for (i = 0; i < 2; i++) seen <= frame_error;
  X_a: cover property (@(posedge clk) disable iff (rst) frame_error);
endmodule
bind uart_rx cov_X u_cov_X (.*);
