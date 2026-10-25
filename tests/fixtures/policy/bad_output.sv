module cov_X (input logic clk, input logic rst, input logic frame_error, output logic busy);
  always @(posedge clk) busy <= 1;
  X_a: cover property (@(posedge clk) disable iff (rst) frame_error);
endmodule
bind uart_rx cov_X u_cov_X (.*);
