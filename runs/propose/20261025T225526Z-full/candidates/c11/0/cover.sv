module cov_P11 (
  input logic clk,
  input logic rst,
  input logic frame_error
);

  P11_rst_clears_frame_error: cover property (@(posedge clk)
    rst && $past(rst) && $past(frame_error) && !frame_error);

endmodule

bind uart_rx cov_P11 u_cov_P11 (.*);
