// Stop bit at prescale 3: busy falls and s_axis_tready rises together,
// exactly 25 clocks after bit_cnt is first seen 0 following 1.
module cov_P26 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [3:0]  bit_cnt,
  input logic        busy,
  input logic        s_axis_tready,
  input logic        s_axis_tvalid
);

  reg [4:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      cnt <= 5'd0;
    end else if (prescale != 16'd3) begin
      cnt <= 5'd0;
    end else if (bit_cnt == 4'd0 && $past(bit_cnt) == 4'd1) begin
      cnt <= 5'd1;
    end else if (cnt != 5'd0 && cnt != 5'd31) begin
      cnt <= cnt + 5'd1;
    end
  end

  P26_tx_busy_fall_ready_rise_25: cover property (@(posedge clk) disable iff (rst)
    cnt == 5'd25 && prescale == 16'd3 && !$past(s_axis_tvalid) &&
    $fell(busy) && $rose(s_axis_tready));

endmodule

bind uart_tx cov_P26 u_cov_P26 (.*);
