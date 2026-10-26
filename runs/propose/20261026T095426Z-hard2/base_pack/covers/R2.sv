// R2: false start bit rejected at the mid-start-bit sample.
module cov_R2 (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg
);

  R2_false_start_rejected: cover property (@(posedge clk) disable iff (rst)
    (prescale_reg == 19'd0) && (bit_cnt == 4'd10) && rxd_reg);

endmodule

bind uart_rx cov_R2 u_cov_R2 (.*);
