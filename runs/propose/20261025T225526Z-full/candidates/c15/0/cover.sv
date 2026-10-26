// Reset applied mid-bit (prescale_reg > 16) must clear the prescaler so that
// s_axis_tready rises on the second clock after reset release.
module cov_P15 (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic        s_axis_tready
);

  logic       rst_q;
  logic       armed;
  logic [1:0] cnt;

  always @(posedge clk) begin
    rst_q <= rst;
    if (rst) begin
      cnt <= 2'd0;
      if (!rst_q) begin
        if (prescale_reg > 19'd16) armed <= 1'b1;
        else armed <= 1'b0;
      end else begin
        if (prescale_reg > 19'd16) armed <= 1'b1;
      end
    end else begin
      if (cnt != 2'd3) cnt <= cnt + 2'd1;
    end
  end

  P15_tx_reset_mid_frame_ready_timing: cover property (@(posedge clk)
    armed && !rst && cnt == 2'd1 && s_axis_tready && !$past(s_axis_tready));

endmodule

bind uart_tx cov_P15 u_cov_P15 (.*);
