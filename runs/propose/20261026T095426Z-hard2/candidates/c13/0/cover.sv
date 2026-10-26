// After a frame error the receiver idles (busy low, rxd high) for at least
// 16 consecutive clocks. The next delivered word is 8'hA5, with no frame
// error in between.
module cov_P13 (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       busy,
  input logic       rxd,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata
);

  // st 0: none; 1: after frame_error, counting idle; 2: idle run >= 16 seen;
  // 3: idle run of exactly 15 seen
  reg [1:0] st;
  reg [4:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      st  <= 2'd0;
      cnt <= 5'd0;
    end else begin
      if (frame_error) begin
        st  <= 2'd1;
        cnt <= 5'd0;
      end else if (st == 2'd1) begin
        if (!busy && rxd) begin
          if (cnt != 5'd31) cnt <= cnt + 5'd1;
        end else if (cnt != 5'd0) begin
          if (cnt >= 5'd16) st <= 2'd2;
          else if (cnt == 5'd15) st <= 2'd3;
          else st <= 2'd0;
          cnt <= 5'd0;
        end
      end
    end
  end

  P13_recover_after_frame_error_idle: cover property (@(posedge clk) disable iff (rst)
    st == 2'd2 && !frame_error && $rose(m_axis_tvalid) && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P13 u_cov_P13 (.*);
