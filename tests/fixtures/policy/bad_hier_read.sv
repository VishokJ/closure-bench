module cov_X (input logic clk, input logic rst, input logic frame_error);
  X_a: cover property (@(posedge clk) uart_rx.frame_error_reg);
endmodule
bind uart_rx cov_X u_cov_X (.*);
