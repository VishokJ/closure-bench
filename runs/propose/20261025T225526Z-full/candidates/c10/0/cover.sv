// P10: reset taken mid-bit with rxd held low; the new start bit is picked up
// promptly, so busy is first seen high on the third clock after rst falls.
module cov_P10 (
  input logic        clk,
  input logic        rst,
  input logic        rxd,
  input logic        busy,
  input logic [18:0] prescale_reg
);

  reg       in_rst;
  reg       seen_mid;
  reg       rxd_low;
  reg       early;
  reg [1:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      in_rst <= 1'b1;
      cnt    <= 2'd0;
      early  <= 1'b0;
      if (!in_rst) begin
        seen_mid <= (prescale_reg > 19'd16) && !rxd;
        rxd_low  <= !rxd;
      end else begin
        if (rxd) rxd_low <= 1'b0;
      end
    end else begin
      in_rst <= 1'b0;
      if (cnt != 2'd3) cnt <= cnt + 2'd1;
      if (rxd) rxd_low <= 1'b0;
      if (busy && (cnt < 2'd2)) early <= 1'b1;
    end
  end

  P10_rx_reset_mid_frame_prompt_restart: cover property (@(posedge clk)
    !rst && (cnt == 2'd2) && busy && !early && seen_mid && rxd_low && !rxd);

endmodule

bind uart_rx cov_P10 u_cov_P10 (.*);
