module cov_X (input logic clk, input logic rst, input logic frame_error);
  helper u_helper ();
  X_a: cover property (@(posedge clk) disable iff (rst) frame_error);
endmodule
bind uart_rx cov_X u_cov_X (.*);
module helper; endmodule
