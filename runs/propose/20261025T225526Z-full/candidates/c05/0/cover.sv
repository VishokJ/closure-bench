// P5: reset taken while the transmitter drives a low bit mid-frame.
// On the next clock the line must be back at mark (txd = 1) and busy must be 0.
module cov_P5 (
  input logic clk,
  input logic rst,
  input logic txd,
  input logic busy
);

  P5_tx_reset_mid_frame_low: cover property (@(posedge clk)
    $past(rst) && !$past(txd) && $past(busy) && txd && !busy);

endmodule

bind uart_tx cov_P5 u_cov_P5 (.*);
