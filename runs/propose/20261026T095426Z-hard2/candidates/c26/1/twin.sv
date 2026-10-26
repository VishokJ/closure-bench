// Twin: same two back-to-back words at prescale 1 and the same clock after
// the second stop bit, but s_axis_tvalid was high, so a third word is taken:
// s_axis_tready rises while busy stays high.
module cov_P26_twin (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [3:0]  bit_cnt,
  input logic        busy,
  input logic        s_axis_tready,
  input logic        s_axis_tvalid
);

  reg [4:0] cnt;
  reg       b2b;

  always @(posedge clk) begin
    if (rst) begin
      cnt <= 5'd0;
      b2b <= 1'b0;
    end else if (prescale != 16'd1) begin
      cnt <= 5'd0;
      b2b <= 1'b0;
    end else begin
      if (bit_cnt == 4'd0 && $past(bit_cnt) == 4'd1) begin
        cnt <= 5'd1;
      end else if (cnt != 5'd0 && cnt != 5'd31) begin
        cnt <= cnt + 5'd1;
      end
      if ($rose(s_axis_tready) && busy && $past(busy) && $past(s_axis_tvalid)) begin
        b2b <= 1'b1;
      end else if (!busy) begin
        b2b <= 1'b0;
      end
    end
  end

  P26_twin_tx_b2b_third_word_ready_rise_9: cover property (@(posedge clk) disable iff (rst)
    b2b && cnt == 5'd9 && prescale == 16'd1 && $past(s_axis_tvalid) &&
    busy && $past(busy) && $rose(s_axis_tready));

endmodule

bind uart_tx cov_P26_twin u_cov_P26_twin (.*);
