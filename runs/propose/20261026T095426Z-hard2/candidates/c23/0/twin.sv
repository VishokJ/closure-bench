// Twin: same two words 8'h12 then 8'h34 at prescale 2, but busy dropped at least
// once between the frames (not back-to-back), so the target cannot hold.
module cov_P23_twin (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        busy,
  input logic        s_axis_tvalid,
  input logic [8:0]  data_reg
);

  reg [7:0] shift;
  reg       p_ok;
  reg       first_any;
  reg       gap;

  always @(posedge clk) begin
    if (rst) begin
      shift     <= 8'h00;
      p_ok      <= 1'b0;
      first_any <= 1'b0;
      gap       <= 1'b0;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && s_axis_tvalid) begin
        shift <= 8'h00;
        p_ok  <= (prescale == 16'd2);
      end else if (prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
        shift <= {txd, shift[7:1]};
        if (bit_cnt == 4'd1) begin
          gap <= 1'b0;
          if (p_ok && busy && ({txd, shift[7:1]} == 8'h12)) first_any <= 1'b1;
          else first_any <= 1'b0;
        end
      end
      if (prescale != 16'd2) begin
        p_ok      <= 1'b0;
        first_any <= 1'b0;
      end
      if (!busy) begin
        gap <= 1'b1;
      end
    end
  end

  P23_twin_tx_prescale2_gap_12_34: cover property (@(posedge clk) disable iff (rst)
    first_any && gap && p_ok && busy && (prescale == 16'd2) &&
    (prescale_reg == 19'd0) && (bit_cnt == 4'd2) &&
    ({data_reg[0], txd, shift[7:2]} == 8'h34));

endmodule

bind uart_tx cov_P23_twin u_cov_P23_twin (.*);
