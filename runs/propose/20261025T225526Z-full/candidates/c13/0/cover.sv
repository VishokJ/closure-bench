module cov_P13 (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic        busy
);

  logic fs_d1;
  logic fs_d2;

  always @(posedge clk) begin
    if (rst) begin
      fs_d1 <= 1'b0;
      fs_d2 <= 1'b0;
    end else begin
      fs_d1 <= (prescale_reg == 19'd0) && (bit_cnt == 4'd10) && rxd_reg;
      fs_d2 <= fs_d1;
    end
  end

  P13_rx_false_start_busy_release: cover property (@(posedge clk) disable iff (rst) fs_d2 && !busy);

endmodule

bind uart_rx cov_P13 u_cov_P13 (.*);
