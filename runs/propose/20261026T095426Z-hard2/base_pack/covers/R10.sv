module cov_R10 (
  input logic clk,
  input logic rst,
  input logic frame_error
);

  R10_rst_clears_frame_error: cover property (@(posedge clk)
    rst && $past(rst) && $past(frame_error) && !frame_error);

endmodule

bind uart_rx cov_R10 u_cov_R10 (.*);
