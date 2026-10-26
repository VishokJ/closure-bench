// T3: s_axis_tready, high while idle, is low on the 2nd and 3rd consecutive
// clocks of a held reset (baseline resets last only two clocks).
module cov_T3 (
  input logic clk,
  input logic rst,
  input logic s_axis_tready
);

  // 0: no tracking; 1: rst seen with tready high (idle);
  // 2: next rst clock had tready low; 3: saturated
  reg [1:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      if (cnt == 2'd0) begin
        if (s_axis_tready) cnt <= 2'd1;
      end else if (cnt != 2'd3) begin
        if (!s_axis_tready) cnt <= cnt + 2'd1;
        else cnt <= 2'd0;
      end
    end else begin
      cnt <= 2'd0;
    end
  end

  T3_tready_low_through_held_reset: cover property (@(posedge clk)
    rst && cnt == 2'd2 && !s_axis_tready);

endmodule

bind uart_tx cov_T3 u_cov_T3 (.*);
