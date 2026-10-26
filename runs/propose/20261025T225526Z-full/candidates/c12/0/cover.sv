// P12: reset sampled while the overrun_error strobe is high; one clock later,
// with reset still asserted, the strobe is low.
module cov_P12 (
  input logic clk,
  input logic rst,
  input logic overrun_error
);

  P12_rst_clears_overrun: cover property (@(posedge clk)
    rst && $past(rst) && $past(overrun_error) && !overrun_error);

endmodule

bind uart_rx cov_P12 u_cov_P12 (.*);
